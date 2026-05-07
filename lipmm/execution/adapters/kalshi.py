"""KalshiExchangeAdapter — adapts feeds.kalshi.KalshiClient to ExchangeClient.

Translation responsibilities:

  - **Type mapping**: Kalshi REST returns `dict[str, Any]`. The adapter
    parses these into typed dataclasses (`Order`, `OrderbookLevels`,
    `Position`, `Balance`).
  - **Unit conversion**: Kalshi uses cents (int strings) for prices and
    `position_fp` / `balance` cents (int) for cash. The adapter exposes
    dollar floats where appropriate.
  - **Error semantics**: Kalshi raises `KalshiResponseError` on 4xx and
    5xx. The protocol contract says: rejection (insufficient funds,
    post-only cross, wrong format) → return None / False; transient error
    (network, 5xx, rate limit) → raise. Adapter inspects status_code to
    distinguish.
  - **Quirks**: don't send `time_in_force` for default GTC (Kalshi 400s
    on it). Use `/portfolio/orders/batched` (with the 'ed' suffix) for
    batch cancel — the existing client already does this correctly.

Lifecycle: adapter owns the underlying `KalshiClient`. Construction takes
auth + base_url; `aopen()` opens the underlying client; `aclose()` closes
it. Tests can inject a pre-built client via `from_client()` to avoid
construction.

What this adapter does NOT do:
  - Series / event listing (that's TickerSource's job, not ExchangeClient).
  - Auth setup beyond accepting a `KalshiAuth` instance — the caller
    constructs auth from API key + private key.
  - Rate limiting (lives inside KalshiClient — already token-bucketed).
"""

from __future__ import annotations

import logging
from typing import Any

from feeds.kalshi.auth import KalshiAuth
from feeds.kalshi.client import KalshiClient
from feeds.kalshi.errors import KalshiResponseError

from lipmm.execution.base import (
    Balance,
    Order,
    OrderbookLevels,
    PlaceOrderRequest,
    Position,
)

logger = logging.getLogger(__name__)


class KalshiExchangeAdapter:
    """Adapts `feeds.kalshi.KalshiClient` to `lipmm.execution.ExchangeClient`."""

    def __init__(
        self,
        *,
        auth: KalshiAuth,
        base_url: str = "https://api.elections.kalshi.com",
    ) -> None:
        self._client = KalshiClient(auth=auth, base_url=base_url)
        self._owned_client = True

    @classmethod
    def from_client(cls, client: KalshiClient) -> "KalshiExchangeAdapter":
        """Construct from a pre-built KalshiClient (useful for tests)."""
        adapter = cls.__new__(cls)
        adapter._client = client
        adapter._owned_client = False
        return adapter

    async def aopen(self) -> None:
        """Open the underlying HTTP client. Call once before using."""
        await self._client.open()

    async def aclose(self) -> None:
        """Close the underlying HTTP client."""
        if self._owned_client:
            await self._client.close()

    async def __aenter__(self) -> "KalshiExchangeAdapter":
        await self.aopen()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    # ── Order lifecycle ─────────────────────────────────────────────

    async def place_order(self, request: PlaceOrderRequest) -> Order | None:
        """POST /portfolio/orders. Returns Order on success, None on 4xx
        rejection (insufficient funds, post-only cross, etc.). Raises on
        5xx or transport error.

        Sub-cent path: when the request carries a `limit_price_t1c` that
        isn't a whole-cent multiple (e.g. 977 = 97.7¢), we send Kalshi
        the fractional `yes_price_dollars: "0.977"` field. If Kalshi
        rejects that (4xx — possibly because the market doesn't accept
        fractional in this range), we fall back ONCE to integer cents
        (rounded). This way a single bad subcent attempt doesn't stop
        quoting on that strike — it just degrades.

        Note: Kalshi default GTC is implicit — we never send
        `time_in_force` for GTC because Kalshi 400s on the field even
        when the value is correct.
        """
        t1c = request.effective_t1c()
        is_subcent = t1c % 10 != 0
        common_kwargs = dict(
            ticker=request.ticker,
            action=request.action,
            side=request.side,
            order_type="limit",
            count=request.count,
            post_only=request.post_only,
        )
        # Try fractional path first when the price is sub-cent.
        if is_subcent:
            yes_price_dollars = f"{t1c / 1000.0:.4f}"
            try:
                resp = await self._client.create_order(
                    **common_kwargs,
                    yes_price_dollars=yes_price_dollars,
                )
                order_dict = resp.get("order", {})
                return _parse_order(
                    order_dict, ticker=request.ticker,
                    action=request.action, side=request.side,
                    limit_price=request.limit_price_cents,
                    limit_price_t1c=t1c,
                    count=request.count,
                )
            except KalshiResponseError as exc:
                if 400 <= (exc.status_code or 0) < 500:
                    logger.warning(
                        "Kalshi rejected sub-cent yes_price_dollars=%s on %s "
                        "(status=%s): body=%s msg=%s — falling back to integer cents",
                        yes_price_dollars, request.ticker,
                        exc.status_code, getattr(exc, "body", None), exc,
                    )
                    # Fall through to integer-cent retry below.
                else:
                    raise

        # Whole-cent path (also the fallback for sub-cent rejections).
        try:
            resp = await self._client.create_order(
                **common_kwargs,
                yes_price=request.limit_price_cents,
            )
        except KalshiResponseError as exc:
            if 400 <= (exc.status_code or 0) < 500:
                # Log the full Kalshi response body so the operator can
                # tell "insufficient collateral" apart from "post-only
                # cross", "tick size violation", "market closed", etc.
                # Without the body we can't diagnose collateral issues.
                logger.warning(
                    "Kalshi place_order rejected: ticker=%s action=%s side=%s "
                    "price=%dc count=%d status=%s body=%s msg=%s",
                    request.ticker, request.action, request.side,
                    request.limit_price_cents, request.count,
                    exc.status_code, getattr(exc, "body", None), exc,
                )
                return None
            raise

        order_dict = resp.get("order", {})
        return _parse_order(order_dict, ticker=request.ticker,
                            action=request.action, side=request.side,
                            limit_price=request.limit_price_cents,
                            limit_price_t1c=t1c,
                            count=request.count)

    async def amend_order(
        self, order_id: str, *,
        new_limit_price_cents: int | None = None,
        new_count: int | None = None,
    ) -> Order | None:
        """POST /portfolio/orders/{id}/amend. Returns Order on success,
        None if Kalshi rejects the amend (it often does — historical 400
        rate is high). Caller is expected to fall back to cancel+place."""
        try:
            resp = await self._client.amend_order(
                order_id,
                yes_price=new_limit_price_cents,
                count=new_count,
            )
        except KalshiResponseError as exc:
            if 400 <= (exc.status_code or 0) < 500:
                logger.info(
                    "Kalshi amend_order rejected (status=%s): %s",
                    exc.status_code, exc,
                )
                return None
            raise

        order_dict = resp.get("order", {})
        if not order_dict:
            return None
        return _parse_order(order_dict)

    async def cancel_order(self, order_id: str) -> bool:
        """DELETE /portfolio/orders/{id}. Returns True on success, False
        if Kalshi 404s (order already gone). Raises on 5xx."""
        try:
            await self._client.cancel_order(order_id)
            return True
        except KalshiResponseError as exc:
            if exc.status_code == 404:
                return False
            if 400 <= (exc.status_code or 0) < 500:
                logger.warning(
                    "Kalshi cancel_order non-404 4xx (status=%s): %s",
                    exc.status_code, exc,
                )
                return False
            raise

    async def cancel_orders(self, order_ids: list[str]) -> dict[str, bool]:
        """Batch cancel via `/portfolio/orders/batched`. Falls back to
        per-order cancellation on batch failure (the historical pattern
        from the soy bot, since the batched endpoint has been flaky)."""
        if not order_ids:
            return {}

        # Try batch first
        try:
            await self._client.batch_cancel_orders(order_ids)
            # Verify by re-querying resting orders — defensive against
            # silent partial success (batch returns 200 but didn't cancel
            # everything)
            try:
                resp = await self._client.get_orders(status="resting", limit=200)
                still_resting = {
                    o.get("order_id") for o in resp.get("orders", [])
                    if o.get("order_id")
                }
                return {
                    oid: oid not in still_resting for oid in order_ids
                }
            except Exception:
                # Verification failed — assume batch worked
                return {oid: True for oid in order_ids}
        except Exception as exc:
            logger.warning(
                "Kalshi batch cancel failed (%s), falling back to per-order",
                exc,
            )

        # Per-order fallback
        out: dict[str, bool] = {}
        for oid in order_ids:
            out[oid] = await self.cancel_order(oid)
        return out

    # ── Reads ───────────────────────────────────────────────────────

    async def get_orderbook(self, ticker: str) -> OrderbookLevels:
        """Snapshot the orderbook for a ticker. Returns OrderbookLevels
        with yes_levels and no_levels as [(price_cents, size), ...] sorted
        highest-first."""
        resp = await self._client.get_orderbook(ticker)
        ob_fp = resp.get("orderbook_fp", {}) or {}
        yes_dollars = ob_fp.get("yes_dollars", []) or []
        no_dollars = ob_fp.get("no_dollars", []) or []
        yes_lv, yes_subcent = _parse_depth(yes_dollars)
        no_lv, no_subcent = _parse_depth(no_dollars)
        has_subcent = yes_subcent or no_subcent
        # Infer a per-range tick schedule from the observed levels.
        # Some Kalshi markets have a "U-shape" schedule (sub-cent at
        # the edges, whole-cent in the middle). Inference is
        # best-effort; a band only flags as sub-cent if at least one
        # observed level there has t1c % 10 != 0.
        tick_schedule = _infer_tick_schedule(yes_lv, no_lv)
        return OrderbookLevels(
            ticker=ticker,
            yes_levels=yes_lv,
            no_levels=no_lv,
            has_subcent_ticks=has_subcent,
            tick_schedule=tick_schedule,
        )

    async def list_resting_orders(self) -> list[Order]:
        """All currently-resting orders for the account."""
        resp = await self._client.get_orders(status="resting", limit=200)
        return [_parse_order(o) for o in resp.get("orders", [])]

    async def list_positions(self) -> list[Position]:
        """All non-zero positions.

        Kalshi /portfolio/positions field semantics (v2):
          position / position_fp:  signed share count (int / float-string)
          market_exposure:         current cost basis on the OPEN position,
                                   in cents — integer. (NOT total_traded,
                                   which is lifetime including closed legs.)
          realized_pnl, fees_paid: cents, integer.

        We derive `avg_cost_cents` as `market_exposure / |position|`
        because Kalshi does not return an explicit avg-cost field. We
        also tolerate a few alternative key names in case of future
        schema drift — `average_cost_cents`, `realized_pnl_dollars`,
        `fees_paid_dollars` — falling through to derivation when they're
        absent or zero.
        """
        def _f(d: dict, *keys: str, default: float = 0.0) -> float:
            for k in keys:
                v = d.get(k)
                if v is None or v == "":
                    continue
                try:
                    return float(v)
                except (TypeError, ValueError):
                    continue
            return default

        resp = await self._client.get_positions(limit=200)
        out: list[Position] = []
        for p in resp.get("market_positions", []):
            qty = int(round(_f(p, "position_fp", "position")))
            if qty == 0:
                continue

            avg_cost_cents = int(round(
                _f(p, "average_cost_cents")  # legacy / hypothetical
            ))
            if avg_cost_cents == 0:
                # Derive from market_exposure (cost basis on open position
                # in cents). Sign of market_exposure mirrors `position` so
                # we take abs to express avg cost as a positive cents.
                exposure = _f(p, "market_exposure")
                if exposure and qty != 0:
                    avg_cost_cents = int(round(abs(exposure) / abs(qty)))

            # Realized PnL: prefer cents-named field per current docs;
            # fall back to dollars-named if a future schema renames it.
            realized_cents = _f(p, "realized_pnl", "realized_pnl_cents")
            if realized_cents:
                realized = realized_cents / 100.0
            else:
                realized = _f(p, "realized_pnl_dollars")

            fees_cents = _f(p, "fees_paid", "fees_paid_cents")
            if fees_cents:
                fees = fees_cents / 100.0
            else:
                fees = _f(p, "fees_paid_dollars")

            out.append(Position(
                ticker=p.get("ticker", ""),
                quantity=qty,
                avg_cost_cents=avg_cost_cents,
                realized_pnl_dollars=realized,
                fees_paid_dollars=fees,
            ))
        return out

    async def get_balance(self) -> Balance:
        """Account cash + portfolio value, in dollars."""
        resp = await self._client.get_balance()
        # Kalshi balance is in cents (int)
        cash_cents = float(resp.get("balance", 0) or 0)
        portfolio_cents = float(resp.get("portfolio_value", 0) or 0)
        return Balance(
            cash_dollars=cash_cents / 100.0,
            portfolio_value_dollars=portfolio_cents / 100.0,
        )


# ── Parsing helpers ───────────────────────────────────────────────────


def _parse_depth(levels: list) -> tuple[list[tuple[int, float]], bool]:
    """Parse Kalshi `[[price_str_dollars, size_str], ...]` into
    `[(price_t1c, size), ...]` sorted highest-first.

    `t1c` = tenths-of-a-cent (10 = 1¢, 1 = 0.1¢). For a normal
    whole-cent market level "0.4500" → 4500/10 = 450 t1c. For a
    sub-cent level "0.9778" → 977.8 → 978 t1c (rounded to nearest
    0.1¢ since Kalshi prices come as 4-decimal dollars).

    Returns `(levels_t1c, has_subcent)`. `has_subcent` is True when
    any level isn't a whole-cent multiple — used by the caller to
    select the right tick schedule and route place_order through
    the fractional path."""
    if not levels:
        return [], False
    parsed: list[tuple[int, float]] = []
    has_subcent = False
    for lv in levels:
        if not isinstance(lv, (list, tuple)) or len(lv) < 2:
            continue
        try:
            # dollars × 1000 = tenths-of-a-cent
            t1c_float = float(lv[0]) * 1000.0
            sz = float(lv[1])
        except (ValueError, TypeError):
            continue
        t1c = int(round(t1c_float))
        # Sub-cent if t1c isn't a whole-cent multiple. Tolerance handled
        # by rounding above (fp noise from "0.4500" still rounds to 4500).
        if t1c % 10 != 0:
            has_subcent = True
        parsed.append((t1c, sz))
    parsed.sort(key=lambda x: -x[0])  # highest-first
    return parsed, has_subcent


def _infer_tick_schedule(
    yes_t1c: list[tuple[int, float]],
    no_t1c: list[tuple[int, float]],
) -> "TickSchedule":
    """Best-effort inference of the per-range tick granularity from
    observed levels.

    Heuristic: check whether any level is sub-cent in three regions:
      - low edge   [10, 100)   (0.1¢..9.9¢)
      - middle     [100, 900)  (10¢..89.9¢)
      - high edge  [900, 990)  (90¢..98.9¢)
    A region is "subcent" iff at least one observed level there has
    `t1c % 10 != 0`. Otherwise it defaults to whole-cent.

    Default fallback (no levels observed in any region): all
    whole-cent — the strategy can fall back gracefully.
    """
    from lipmm.execution.base import TickSchedule  # local import to avoid cycle

    all_levels = list(yes_t1c) + list(no_t1c)
    bands = [(10, 100), (100, 900), (900, 990)]
    schedule: TickSchedule = []
    for lo, hi in bands:
        in_band = [t for (t, _) in all_levels if lo <= t < hi]
        if any(t % 10 != 0 for t in in_band):
            schedule.append((lo, hi, 1))   # sub-cent in this band
        else:
            schedule.append((lo, hi, 10))  # whole-cent in this band
    return schedule


def _parse_order(
    o: dict[str, Any], *,
    ticker: str | None = None,
    action: str | None = None,
    side: str | None = None,
    limit_price: int | None = None,
    limit_price_t1c: int | None = None,
    count: int | None = None,
) -> Order:
    """Parse a Kalshi order dict into an Order dataclass.

    Falls back to the override kwargs when fields aren't present in the
    Kalshi response (e.g., create_order's response sometimes omits some
    fields). Caller passes overrides matching the place_order request.
    """
    oid = o.get("order_id", "")
    parsed_action = o.get("action") or action or "buy"
    parsed_side = o.get("side") or side or "yes"
    parsed_ticker = o.get("ticker") or ticker or ""
    # Kalshi inconsistency: create_order returns `yes_price` as cents
    # (int), but /portfolio/orders returns `yes_price_dollars` as a
    # string like "0.4500". Check the cents field first; fall through
    # to the dollar string field; finally to the kwarg.
    parsed_t1c: int | None = limit_price_t1c
    if "yes_price" in o and o["yes_price"] is not None:
        try:
            parsed_limit = int(o["yes_price"])
            if parsed_t1c is None:
                parsed_t1c = parsed_limit * 10
        except (TypeError, ValueError):
            parsed_limit = limit_price or 0
    elif "yes_price_dollars" in o and o["yes_price_dollars"] is not None:
        # "0.4500" → 45 cents; "0.9778" → 977.8 → 978 t1c → 98 cents (rounded)
        try:
            t1c_from_str = int(round(float(o["yes_price_dollars"]) * 1000))
            parsed_t1c = t1c_from_str
            parsed_limit = (t1c_from_str + 5) // 10
        except (TypeError, ValueError):
            parsed_limit = limit_price or 0
    elif "no_price_dollars" in o and o["no_price_dollars"] is not None:
        # Some sell-side orders only return no_price_dollars; convert
        # via (1000 - no_t1c) for yes equivalent.
        try:
            no_t1c = int(round(float(o["no_price_dollars"]) * 1000))
            yes_t1c = 1000 - no_t1c
            parsed_t1c = yes_t1c
            parsed_limit = (yes_t1c + 5) // 10
        except (TypeError, ValueError):
            parsed_limit = limit_price or 0
    elif limit_price is not None:
        parsed_limit = limit_price
        if parsed_t1c is None:
            parsed_t1c = limit_price * 10
    else:
        parsed_limit = 0
    if "remaining_count" in o and o["remaining_count"] is not None:
        try:
            parsed_remaining = int(o["remaining_count"])
        except (ValueError, TypeError):
            parsed_remaining = count or 0
    elif "remaining_count_fp" in o and o["remaining_count_fp"] is not None:
        try:
            parsed_remaining = int(round(float(o["remaining_count_fp"])))
        except (ValueError, TypeError):
            parsed_remaining = count or 0
    else:
        parsed_remaining = count or 0
    parsed_status = o.get("status", "resting")
    return Order(
        order_id=oid,
        ticker=parsed_ticker,
        action=parsed_action,  # type: ignore[arg-type]
        side=parsed_side,  # type: ignore[arg-type]
        limit_price_cents=parsed_limit,
        remaining_count=parsed_remaining,
        status=parsed_status,
        limit_price_t1c=parsed_t1c,
    )
