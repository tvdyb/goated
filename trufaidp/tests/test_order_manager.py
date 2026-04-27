from __future__ import annotations

from dataclasses import dataclass

from trufaidp.kalshi import OrderId, Side
from trufaidp.mm.order_manager import OrderManager
from trufaidp.mm.quoter import Quote


@dataclass
class _StubClient:
    placed: list = None
    cancelled: list = None
    next_id: int = 0

    def __post_init__(self):
        self.placed = []
        self.cancelled = []

    def place_order(self, *, ticker, side, qty, price_cents, client_order_id, post_only):
        self.placed.append((ticker, side, qty, price_cents, post_only))
        self.next_id += 1
        return OrderId(f"id-{self.next_id}")

    def cancel_order(self, order_id):
        oid = order_id.value if hasattr(order_id, "value") else order_id
        self.cancelled.append(oid)

    def close(self):
        pass


def test_no_op_when_quotes_unchanged():
    client = _StubClient()
    om = OrderManager(client)

    desired = [Quote("K", Side.YES_BUY, 42, 5), Quote("K", Side.NO_BUY, 42, 5)]
    om.reconcile(desired)
    assert len(client.placed) == 2
    client.placed.clear()

    om.reconcile(desired)
    assert client.placed == []
    assert client.cancelled == []


def test_replaces_when_price_changes():
    client = _StubClient()
    om = OrderManager(client)

    om.reconcile([Quote("K", Side.YES_BUY, 42, 5)])
    om.reconcile([Quote("K", Side.YES_BUY, 43, 5)])
    assert len(client.cancelled) == 1
    assert len(client.placed) == 2


def test_cancels_when_quote_disappears():
    client = _StubClient()
    om = OrderManager(client)

    om.reconcile([Quote("K", Side.YES_BUY, 42, 5), Quote("K", Side.NO_BUY, 42, 5)])
    om.reconcile([Quote("K", Side.YES_BUY, 42, 5)])  # no_buy gone
    assert len(client.cancelled) == 1


def test_cancel_all():
    client = _StubClient()
    om = OrderManager(client)

    om.reconcile([Quote("K", Side.YES_BUY, 42, 5), Quote("K", Side.NO_BUY, 42, 5)])
    n = om.cancel_all()
    assert n == 2
    assert om.open_orders == {}


def test_apply_fill_partial():
    client = _StubClient()
    om = OrderManager(client)
    om.reconcile([Quote("K", Side.YES_BUY, 42, 5)])
    om.apply_fill("K", Side.YES_BUY, 2)
    remaining = om.open_orders[("K", Side.YES_BUY)]
    assert remaining.qty == 3


def test_apply_fill_full_clears():
    client = _StubClient()
    om = OrderManager(client)
    om.reconcile([Quote("K", Side.YES_BUY, 42, 5)])
    om.apply_fill("K", Side.YES_BUY, 5)
    assert ("K", Side.YES_BUY) not in om.open_orders
