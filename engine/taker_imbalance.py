"""Taker-imbalance detector for Kalshi markets.

Maintains a rolling window of trade-side classifications (buy-initiated vs
sell-initiated) and signals when imbalance exceeds a threshold, triggering
withdrawal of the adverse side.

Trade classification: compare trade price to midpoint.
- price > mid -> buy-initiated
- price < mid -> sell-initiated
- price == mid -> skip (ambiguous)

Signal decays after a configurable cooldown.

Closes: new gap (F4-specific asymmetric defense, F4-ACT-16).

Non-negotiables: no pandas, fail-loud, synchronous, type hints.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ImbalanceSignal:
    """Signal emitted when taker imbalance is detected.

    Attributes:
        withdraw_side: "bid" or "ask" — the side to withdraw.
            "bid" means sell-initiated flow dominates (withdraw bids to
            avoid buying into a downdraft).
            "ask" means buy-initiated flow dominates (withdraw asks to
            avoid selling into a rally).
        ratio: Imbalance ratio in [0, 1]. Higher = more imbalanced.
        expires_at: Unix timestamp when signal expires.
    """

    withdraw_side: str
    ratio: float
    expires_at: float


@dataclass(slots=True)
class ImbalanceConfig:
    """Configuration for the taker-imbalance detector.

    Attributes:
        window_seconds: Rolling window duration for trade classification.
        threshold: Imbalance ratio threshold to trigger signal.
        cooldown_seconds: Duration for which the signal persists after
            the imbalance drops below threshold.
        min_trades: Minimum number of trades in the window before
            computing imbalance (avoid noise on thin data).
    """

    window_seconds: float = 60.0
    threshold: float = 0.7
    cooldown_seconds: float = 120.0
    min_trades: int = 5


class TakerImbalanceDetector:
    """Rolling-window taker-imbalance detector.

    Usage::

        detector = TakerImbalanceDetector()

        # On each trade from WS:
        detector.record_trade(price_cents=52, mid_cents=50, now=time.time())

        # On each quote cycle:
        signal = detector.current_signal(now=time.time())
        if signal is not None:
            # withdraw signal.withdraw_side
    """

    def __init__(self, config: ImbalanceConfig | None = None) -> None:
        self._config = config or ImbalanceConfig()
        # Deque of (timestamp, side) where side is 1 for buy, -1 for sell
        self._trades: deque[tuple[float, int]] = deque()
        self._last_signal: ImbalanceSignal | None = None

    @property
    def config(self) -> ImbalanceConfig:
        return self._config

    def record_trade(
        self,
        price_cents: int,
        mid_cents: int,
        now: float | None = None,
    ) -> None:
        """Record a trade and classify as buy or sell initiated.

        Args:
            price_cents: Trade price in cents.
            mid_cents: Orderbook midpoint in cents at trade time.
            now: Current timestamp (defaults to time.time()).

        Trades at the midpoint are ambiguous and skipped.
        """
        if now is None:
            now = time.time()

        if price_cents > mid_cents:
            side = 1  # buy-initiated
        elif price_cents < mid_cents:
            side = -1  # sell-initiated
        else:
            return  # ambiguous, skip

        self._trades.append((now, side))

    def _prune(self, now: float) -> None:
        """Remove trades older than the window."""
        cutoff = now - self._config.window_seconds
        while self._trades and self._trades[0][0] < cutoff:
            self._trades.popleft()

    def compute_imbalance(self, now: float | None = None) -> tuple[float, int, int]:
        """Compute current imbalance ratio.

        Returns:
            (ratio, n_buys, n_sells) where ratio = |buys - sells| / (buys + sells).
            Returns (0.0, 0, 0) if insufficient data.
        """
        if now is None:
            now = time.time()
        self._prune(now)

        n_buys = 0
        n_sells = 0
        for _, side in self._trades:
            if side > 0:
                n_buys += 1
            else:
                n_sells += 1

        total = n_buys + n_sells
        if total < self._config.min_trades:
            return 0.0, n_buys, n_sells

        ratio = abs(n_buys - n_sells) / total
        return ratio, n_buys, n_sells

    def current_signal(self, now: float | None = None) -> ImbalanceSignal | None:
        """Check if an imbalance signal is active.

        Returns:
            ImbalanceSignal if imbalance is detected or a prior signal
            hasn't expired yet. None if normal.
        """
        if now is None:
            now = time.time()

        ratio, n_buys, n_sells = self.compute_imbalance(now)

        if ratio >= self._config.threshold and (n_buys + n_sells) >= self._config.min_trades:
            # Determine which side to withdraw
            if n_buys > n_sells:
                # Buy-initiated dominance -> price likely going up -> withdraw asks
                withdraw_side = "ask"
            else:
                # Sell-initiated dominance -> price likely going down -> withdraw bids
                withdraw_side = "bid"

            self._last_signal = ImbalanceSignal(
                withdraw_side=withdraw_side,
                ratio=ratio,
                expires_at=now + self._config.cooldown_seconds,
            )
            return self._last_signal

        # Check if a prior signal is still in cooldown
        if self._last_signal is not None and now < self._last_signal.expires_at:
            return self._last_signal

        # No active signal
        self._last_signal = None
        return None

    def reset(self) -> None:
        """Clear all state."""
        self._trades.clear()
        self._last_signal = None
