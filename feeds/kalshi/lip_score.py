"""LIP Score Tracker -- compute snapshot-level LIP Score per market.

Computes our own snapshot Score continuously (per market, per side),
estimates visible competitor Score from the public orderbook, projects
rolling expected pool share, and emits telemetry for ACT-LIP-PNL.

Scoring formula (from F3 section 1):
  Score(market, snapshot) = SUM_orders [order_size * distance_multiplier(order)]
  distance_multiplier in [0.0, 1.0]: 1.0 at best bid/ask, decays toward 0.

Non-negotiables enforced:
  - No pandas
  - Type hints on all public interfaces
  - Fail-loud on missing orderbook data
  - numba.njit on hot-path distance multiplier
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
from numba import njit

logger = logging.getLogger(__name__)

# ── Distance multiplier (hot path, numba-accelerated) ──────────────


@njit(cache=True)
def _linear_distance_multiplier(
    order_price_cents: int,
    best_price_cents: int,
    decay_ticks: int,
) -> float:
    """Linear decay distance multiplier.

    Returns 1.0 at best price, decays linearly to 0.0 over decay_ticks.
    Orders beyond decay_ticks contribute 0.0.

    All prices in integer cents (1 cent = 1 tick for Kalshi).
    """
    distance = abs(order_price_cents - best_price_cents)
    if distance == 0:
        return 1.0
    if distance >= decay_ticks:
        return 0.0
    return 1.0 - float(distance) / float(decay_ticks)


@njit(cache=True)
def _compute_score_array(
    prices_cents: np.ndarray,
    sizes: np.ndarray,
    best_price_cents: int,
    decay_ticks: int,
) -> float:
    """Compute LIP score for an array of (price, size) pairs.

    Args:
        prices_cents: 1D int array of order prices in cents.
        sizes: 1D float array of order sizes (contract counts).
        best_price_cents: Best bid or best ask price in cents.
        decay_ticks: Number of ticks over which multiplier decays to 0.

    Returns:
        Total score as float.
    """
    total = 0.0
    n = len(prices_cents)
    for i in range(n):
        dist = abs(prices_cents[i] - best_price_cents)
        if dist == 0:
            mult = 1.0
        elif dist >= decay_ticks:
            mult = 0.0
        else:
            mult = 1.0 - float(dist) / float(decay_ticks)
        total += sizes[i] * mult
    return total


# ── Public distance multiplier (non-numba wrapper for flexibility) ──


DEFAULT_DECAY_TICKS: int = 5
"""Default linear decay: 5 ticks from inside. Per OD-34' working default."""


def distance_multiplier(
    order_price_cents: int,
    best_price_cents: int,
    decay_ticks: int = DEFAULT_DECAY_TICKS,
) -> float:
    """Compute distance multiplier for a single order.

    Args:
        order_price_cents: Order price in integer cents.
        best_price_cents: Best bid or best ask in integer cents.
        decay_ticks: Number of ticks for linear decay to 0.

    Returns:
        Multiplier in [0.0, 1.0].

    Raises:
        ValueError: If decay_ticks < 1.
    """
    if decay_ticks < 1:
        raise ValueError(f"decay_ticks must be >= 1, got {decay_ticks}")
    return _linear_distance_multiplier(order_price_cents, best_price_cents, decay_ticks)


# ── Orderbook side state ───────────────────────────────────────────


@dataclass(slots=True)
class OrderbookSide:
    """Maintained state for one side (yes/no) of a market's orderbook.

    Levels are stored as {price_cents: size}. Updated incrementally
    from WS orderbook_delta events.
    """

    levels: dict[int, float] = field(default_factory=dict)

    @property
    def best_price(self) -> int | None:
        """Best (highest for bids, lowest for asks) price with size > 0.

        For bids: highest price. For asks: lowest price.
        Caller must specify interpretation via bid=True/False on
        MarketOrderbook.
        """
        active = [p for p, s in self.levels.items() if s > 0]
        return max(active) if active else None

    def total_size(self) -> float:
        """Sum of all resting size across all levels."""
        return sum(s for s in self.levels.values() if s > 0)

    def apply_delta(self, price_cents: int, delta: float) -> None:
        """Apply an incremental size delta to a price level."""
        current = self.levels.get(price_cents, 0.0)
        new_size = current + delta
        if new_size <= 0:
            self.levels.pop(price_cents, None)
        else:
            self.levels[price_cents] = new_size

    def set_level(self, price_cents: int, size: float) -> None:
        """Set absolute size at a price level (for snapshots)."""
        if size <= 0:
            self.levels.pop(price_cents, None)
        else:
            self.levels[price_cents] = size

    def clear(self) -> None:
        """Clear all levels."""
        self.levels.clear()

    def to_arrays(self) -> tuple[np.ndarray, np.ndarray]:
        """Export active levels as parallel (prices, sizes) numpy arrays.

        Returns:
            Tuple of (prices_cents int32 array, sizes float64 array).
            Empty arrays if no active levels.
        """
        active = [(p, s) for p, s in self.levels.items() if s > 0]
        if not active:
            return np.array([], dtype=np.int32), np.array([], dtype=np.float64)
        prices = np.array([p for p, _ in active], dtype=np.int32)
        sizes = np.array([s for _, s in active], dtype=np.float64)
        return prices, sizes


# ── Market orderbook ───────────────────────────────────────────────


class MarketOrderbookError(Exception):
    """Raised when orderbook data is missing or stale."""


@dataclass(slots=True)
class MarketOrderbook:
    """Full orderbook state for a single market.

    Maintains yes-side and no-side levels. Best bid is the highest
    yes price; best ask is derived from the lowest no price
    (ask_yes = 100 - best_no in cents).

    In Kalshi's binary model:
      - Yes bid = highest yes price with resting buy orders
      - Yes ask = lowest yes price with resting sell orders
        (equivalent to 100 - highest no price)

    For LIP scoring we track both yes and no sides separately.
    """

    market_ticker: str
    yes_side: OrderbookSide = field(default_factory=OrderbookSide)
    no_side: OrderbookSide = field(default_factory=OrderbookSide)
    last_update_ns: int = 0

    def best_bid_cents(self) -> int:
        """Best yes bid (highest yes price with resting size).

        Raises:
            MarketOrderbookError: If no bid levels exist.
        """
        best = self.yes_side.best_price
        if best is None:
            raise MarketOrderbookError(
                f"No yes-side bid levels for {self.market_ticker}"
            )
        return best

    def best_ask_cents(self) -> int:
        """Best yes ask (lowest yes price with resting sell orders).

        In Kalshi, selling No at price P is equivalent to buying Yes at
        (100 - P). The best yes ask is the lowest resting yes sell level.
        We derive it from the no side: best_yes_ask = 100 - best_no_bid.

        If yes_side has explicit ask levels (from observed orderbook),
        prefer those. Otherwise derive from no_side.

        Raises:
            MarketOrderbookError: If no ask levels exist.
        """
        # The no_side best_price represents the highest no price with size.
        # In Kalshi: no_price + yes_price = 100 cents.
        # So best yes ask = 100 - highest_no_price.
        no_best = self.no_side.best_price
        if no_best is not None:
            return 100 - no_best
        raise MarketOrderbookError(
            f"No ask levels derivable for {self.market_ticker}"
        )

    def mark_updated(self) -> None:
        """Record that the orderbook was updated just now."""
        self.last_update_ns = time.monotonic_ns()


# ── Our resting orders ─────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class RestingOrder:
    """A single resting order of ours on a market.

    Attributes:
        order_id: Unique order identifier.
        market_ticker: Market this order is on.
        side: 'yes' or 'no'.
        price_cents: Order price in integer cents.
        remaining_size: Remaining resting size (contracts).
    """

    order_id: str
    market_ticker: str
    side: str  # "yes" or "no"
    price_cents: int
    remaining_size: float


# ── Score snapshot telemetry ───────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ScoreSnapshot:
    """Telemetry record for one market at one snapshot instant.

    Emitted every scoring tick (1Hz default). Consumed by the
    attribution layer (ACT-LIP-PNL, Wave 1).
    """

    market_ticker: str
    timestamp_ns: int
    our_score: float
    total_score: float
    projected_share: float
    our_resting_size_yes: float
    our_resting_size_no: float
    target_size: float
    below_target_yes: bool
    below_target_no: bool


# ── Rolling window tracker ─────────────────────────────────────────


@dataclass(slots=True)
class RollingScoreWindow:
    """Tracks score snapshots over a configurable time window.

    Uses a bounded deque of (timestamp_ns, our_score, total_score)
    tuples. Provides efficient mean/std over the window.
    """

    window_ns: int
    _entries: deque[tuple[int, float, float]] = field(
        default_factory=deque, repr=False
    )

    def add(self, timestamp_ns: int, our_score: float, total_score: float) -> None:
        """Add a score snapshot to the rolling window."""
        self._entries.append((timestamp_ns, our_score, total_score))
        self._evict(timestamp_ns)

    def _evict(self, now_ns: int) -> None:
        """Remove entries older than window_ns from now."""
        cutoff = now_ns - self.window_ns
        while self._entries and self._entries[0][0] < cutoff:
            self._entries.popleft()

    @property
    def count(self) -> int:
        return len(self._entries)

    def mean_share(self) -> float:
        """Mean of (our_score / total_score) over the window.

        Snapshots where total_score == 0 are excluded (no liquidity).
        Returns 0.0 if no valid snapshots.
        """
        if not self._entries:
            return 0.0
        shares = []
        for _, our, total in self._entries:
            if total > 0:
                shares.append(our / total)
        if not shares:
            return 0.0
        return float(np.mean(shares))

    def std_share(self) -> float:
        """Standard deviation of share over the window.

        Returns 0.0 if fewer than 2 valid snapshots.
        """
        if not self._entries:
            return 0.0
        shares = []
        for _, our, total in self._entries:
            if total > 0:
                shares.append(our / total)
        if len(shares) < 2:
            return 0.0
        return float(np.std(shares, ddof=1))

    def mean_our_score(self) -> float:
        """Mean of our_score over the window."""
        if not self._entries:
            return 0.0
        return float(np.mean([s[1] for s in self._entries]))

    def mean_total_score(self) -> float:
        """Mean of total_score over the window."""
        if not self._entries:
            return 0.0
        return float(np.mean([s[2] for s in self._entries]))


# ── Score computation engine ───────────────────────────────────────

_1H_NS = 3_600_000_000_000
_1D_NS = 86_400_000_000_000


class LIPScoreTracker:
    """Per-market LIP Score Tracker.

    Tracks our resting orders, the visible orderbook, and computes
    score snapshots on demand.

    Usage::

        tracker = LIPScoreTracker(
            market_ticker="KXSOYBEANW-26APR27-17",
            target_size=100.0,
            decay_ticks=5,
        )
        # Feed orderbook state
        tracker.orderbook.yes_side.set_level(50, 200.0)
        tracker.orderbook.no_side.set_level(52, 150.0)
        tracker.orderbook.mark_updated()

        # Feed our orders
        tracker.set_our_orders([
            RestingOrder("o1", "KXSOYBEANW-26APR27-17", "yes", 50, 50.0),
        ])

        # Compute snapshot
        snap = tracker.compute_snapshot()
    """

    def __init__(
        self,
        market_ticker: str,
        *,
        target_size: float = 100.0,
        decay_ticks: int = DEFAULT_DECAY_TICKS,
        pool_size_usd: float = 0.0,
    ) -> None:
        if decay_ticks < 1:
            raise ValueError(f"decay_ticks must be >= 1, got {decay_ticks}")
        if target_size < 0:
            raise ValueError(f"target_size must be >= 0, got {target_size}")

        self.market_ticker = market_ticker
        self.target_size = target_size
        self.decay_ticks = decay_ticks
        self.pool_size_usd = pool_size_usd

        self.orderbook = MarketOrderbook(market_ticker=market_ticker)
        self._our_orders: list[RestingOrder] = []

        # Rolling windows: 1 hour and 1 day
        self.window_1h = RollingScoreWindow(window_ns=_1H_NS)
        self.window_1d = RollingScoreWindow(window_ns=_1D_NS)

        # Telemetry callback (for attribution layer)
        self._telemetry_callbacks: list[Callable[[ScoreSnapshot], None]] = []

    def on_telemetry(self, callback: Callable[[ScoreSnapshot], None]) -> None:
        """Register a callback for score snapshot telemetry."""
        self._telemetry_callbacks.append(callback)

    def set_our_orders(self, orders: list[RestingOrder]) -> None:
        """Replace the set of our resting orders for this market.

        Args:
            orders: List of our current resting orders. All must have
                market_ticker matching this tracker's market.

        Raises:
            ValueError: If any order has a mismatched market_ticker.
        """
        for o in orders:
            if o.market_ticker != self.market_ticker:
                raise ValueError(
                    f"Order {o.order_id} has ticker {o.market_ticker}, "
                    f"expected {self.market_ticker}"
                )
        self._our_orders = list(orders)

    def _our_orders_by_side(self, side: str) -> list[RestingOrder]:
        """Filter our orders by side."""
        return [o for o in self._our_orders if o.side == side]

    def _compute_side_score(
        self,
        prices: np.ndarray,
        sizes: np.ndarray,
        best_price_cents: int,
    ) -> float:
        """Compute score for a set of price/size arrays against a best price."""
        if len(prices) == 0:
            return 0.0
        return _compute_score_array(prices, sizes, best_price_cents, self.decay_ticks)

    def compute_our_score(self) -> float:
        """Compute our total LIP score across both sides.

        Raises:
            MarketOrderbookError: If orderbook has no bid or ask levels.
        """
        total = 0.0

        # Yes-side score: our yes orders scored against best yes bid
        yes_orders = self._our_orders_by_side("yes")
        if yes_orders:
            best_bid = self.orderbook.best_bid_cents()
            prices = np.array([o.price_cents for o in yes_orders], dtype=np.int32)
            sizes = np.array([o.remaining_size for o in yes_orders], dtype=np.float64)
            total += self._compute_side_score(prices, sizes, best_bid)

        # No-side score: our no orders scored against best no price
        no_orders = self._our_orders_by_side("no")
        if no_orders:
            no_best = self.orderbook.no_side.best_price
            if no_best is None:
                raise MarketOrderbookError(
                    f"No no-side levels for {self.market_ticker}"
                )
            prices = np.array([o.price_cents for o in no_orders], dtype=np.int32)
            sizes = np.array([o.remaining_size for o in no_orders], dtype=np.float64)
            total += self._compute_side_score(prices, sizes, no_best)

        return total

    def compute_total_score(self) -> float:
        """Compute total visible score from orderbook (all participants).

        Sums score contributions from all visible levels on both sides.

        Raises:
            MarketOrderbookError: If orderbook is empty.
        """
        total = 0.0

        # Yes side: all levels scored against best yes bid
        yes_prices, yes_sizes = self.orderbook.yes_side.to_arrays()
        if len(yes_prices) > 0:
            best_bid = self.orderbook.best_bid_cents()
            total += self._compute_side_score(yes_prices, yes_sizes, best_bid)

        # No side: all levels scored against best no price
        no_prices, no_sizes = self.orderbook.no_side.to_arrays()
        if len(no_prices) > 0:
            no_best = self.orderbook.no_side.best_price
            if no_best is None:
                raise MarketOrderbookError(
                    f"No no-side levels for {self.market_ticker}"
                )
            total += self._compute_side_score(no_prices, no_sizes, no_best)

        return total

    def compute_snapshot(
        self,
        timestamp_ns: int | None = None,
    ) -> ScoreSnapshot:
        """Compute a full score snapshot for this market.

        Args:
            timestamp_ns: Snapshot timestamp in nanoseconds. Defaults to
                monotonic clock.

        Returns:
            ScoreSnapshot with all computed fields.

        Raises:
            MarketOrderbookError: If orderbook data is missing.
        """
        if timestamp_ns is None:
            timestamp_ns = time.monotonic_ns()

        our_score = self.compute_our_score()
        total_score = self.compute_total_score()

        # Projected share: guard against zero total
        if total_score > 0:
            projected_share = our_score / total_score
        else:
            projected_share = 0.0

        # Our resting size per side
        our_yes_size = sum(o.remaining_size for o in self._our_orders_by_side("yes"))
        our_no_size = sum(o.remaining_size for o in self._our_orders_by_side("no"))

        snap = ScoreSnapshot(
            market_ticker=self.market_ticker,
            timestamp_ns=timestamp_ns,
            our_score=our_score,
            total_score=total_score,
            projected_share=projected_share,
            our_resting_size_yes=our_yes_size,
            our_resting_size_no=our_no_size,
            target_size=self.target_size,
            below_target_yes=our_yes_size < self.target_size,
            below_target_no=our_no_size < self.target_size,
        )

        # Update rolling windows
        self.window_1h.add(timestamp_ns, our_score, total_score)
        self.window_1d.add(timestamp_ns, our_score, total_score)

        # Emit telemetry
        for cb in self._telemetry_callbacks:
            cb(snap)

        return snap

    def projected_reward(self, window: RollingScoreWindow | None = None) -> float:
        """Project LIP reward based on rolling mean share and pool size.

        Args:
            window: Rolling window to use. Defaults to 1-day window.

        Returns:
            Projected reward in USD.
        """
        w = window or self.window_1d
        return w.mean_share() * self.pool_size_usd

    def below_target_size(self, side: str) -> bool:
        """Check if our resting size on a side is below Target Size.

        Args:
            side: 'yes' or 'no'.

        Returns:
            True if our total resting size on that side is below target_size.
        """
        orders = self._our_orders_by_side(side)
        total = sum(o.remaining_size for o in orders)
        return total < self.target_size
