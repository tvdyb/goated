"""Order lifecycle: diff desired quotes vs open orders, idempotent
cancel+place, fill bookkeeping.

The MM loop produces a fresh list of `Quote` objects each cycle from
the quoter. The order manager:
  1. Indexes existing open orders by (ticker, side).
  2. For each desired quote: if an open order at the same (ticker,
     side, price, qty) already exists, leave it (preserves queue
     priority — re-placing kicks us to the back). Otherwise cancel
     the old one and place new.
  3. For any (ticker, side) with no desired quote: cancel.

Queue priority is the dominant LIP variable per Kalshi's reward math
(per-second snapshot of resting size at each level). So we ONLY
cancel when price/qty actually changed — a no-op cycle should be a
no-op on the wire.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from trufaidp.kalshi import KalshiClient, OrderId, Side
from trufaidp.mm.quoter import Quote


_log = logging.getLogger("trufaidp.mm.order_manager")


@dataclass(frozen=True, slots=True)
class OpenOrder:
    order_id: OrderId
    ticker: str
    side: Side
    price_cents: int
    qty: int


class OrderManager:
    def __init__(self, client: KalshiClient, *, dry_run: bool = False) -> None:
        self._client = client
        self._dry_run = dry_run
        self._open: dict[tuple[str, Side], OpenOrder] = {}

    @property
    def open_orders(self) -> dict[tuple[str, Side], OpenOrder]:
        return dict(self._open)

    def reconcile(self, desired: list[Quote]) -> tuple[int, int]:
        """Cancel stale, place new. Returns (cancels, placements)."""
        wanted: dict[tuple[str, Side], Quote] = {(q.ticker, q.side): q for q in desired}

        cancels = 0
        placements = 0

        for key, existing in list(self._open.items()):
            target = wanted.get(key)
            if target is None or target.price_cents != existing.price_cents or target.qty != existing.qty:
                self._cancel(existing)
                cancels += 1

        for key, q in wanted.items():
            if key in self._open:
                existing = self._open[key]
                if existing.price_cents == q.price_cents and existing.qty == q.qty:
                    continue
            self._place(q)
            placements += 1

        return cancels, placements

    def cancel_all(self) -> int:
        n = 0
        for existing in list(self._open.values()):
            self._cancel(existing)
            n += 1
        return n

    def apply_fill(self, ticker: str, side: Side, qty: int) -> None:
        key = (ticker, side)
        existing = self._open.get(key)
        if existing is None:
            return
        remaining = existing.qty - qty
        if remaining <= 0:
            self._open.pop(key, None)
        else:
            self._open[key] = OpenOrder(
                order_id=existing.order_id,
                ticker=existing.ticker,
                side=existing.side,
                price_cents=existing.price_cents,
                qty=remaining,
            )

    def _cancel(self, existing: OpenOrder) -> None:
        key = (existing.ticker, existing.side)
        if self._dry_run:
            _log.info("DRY cancel %s %s id=%s", existing.ticker, existing.side.value, existing.order_id.value)
            self._open.pop(key, None)
            return
        try:
            self._client.cancel_order(existing.order_id)
        except Exception as exc:
            _log.warning("cancel failed for %s: %s", existing.order_id.value, exc)
        finally:
            self._open.pop(key, None)

    def _place(self, q: Quote) -> None:
        key = (q.ticker, q.side)
        cid = uuid.uuid4().hex
        if self._dry_run:
            _log.info("DRY place %s %s qty=%d @ %dc cid=%s", q.ticker, q.side.value, q.qty, q.price_cents, cid)
            self._open[key] = OpenOrder(OrderId(f"dry-{cid}"), q.ticker, q.side, q.price_cents, q.qty)
            return
        oid = self._client.place_order(
            ticker=q.ticker, side=q.side, qty=q.qty, price_cents=q.price_cents,
            client_order_id=cid, post_only=True,
        )
        self._open[key] = OpenOrder(oid, q.ticker, q.side, q.price_cents, q.qty)
