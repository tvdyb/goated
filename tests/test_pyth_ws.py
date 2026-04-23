"""Pyth Hermes message parsing — no network I/O, just the ingest path."""

from __future__ import annotations

import pytest

from feeds.pyth_ws import (
    MalformedPythMessageError,
    PythHermesFeed,
    UnknownFeedError,
)
from state.tick_store import TickStore

FEED_ID = "0xe62df6c8b4a85fe1a67db44dc12de5db330f7ac66b72dc658afedf0f4a415b43"


def _make_feed() -> tuple[PythHermesFeed, TickStore]:
    store = TickStore()
    feed = PythHermesFeed(
        endpoint="wss://test.invalid",
        feed_id_to_commodity={FEED_ID: "wti"},
        tick_store=store,
    )
    return feed, store


def test_ingest_price_update_pushes_tick():
    feed, store = _make_feed()
    msg = {
        "type": "price_update",
        "price_feed": {
            "id": FEED_ID,
            "price": {
                "price": "7500000000",  # 75.0 at expo -8
                "conf": "1000000",
                "expo": -8,
                "publish_time": 1745000000,
                "num_publishers": 7,
            },
        },
    }
    result = feed.ingest_message(msg)
    assert result is not None
    commodity, seq = result
    assert commodity == "wti"
    assert seq == 1
    latest = store.latest("wti")
    assert latest.price == pytest.approx(75.0)
    assert latest.n_publishers == 7
    assert latest.ts_ns == 1745000000 * 1_000_000_000


def test_ingest_non_price_update_returns_none():
    feed, _ = _make_feed()
    assert feed.ingest_message({"type": "heartbeat"}) is None


def test_ingest_unknown_feed_raises():
    feed, _ = _make_feed()
    bad = {
        "type": "price_update",
        "price_feed": {
            "id": "0xdeadbeef",
            "price": {"price": "1", "conf": "0", "expo": 0, "publish_time": 1},
        },
    }
    with pytest.raises(UnknownFeedError):
        feed.ingest_message(bad)


def test_ingest_missing_price_block_raises():
    feed, _ = _make_feed()
    with pytest.raises(MalformedPythMessageError):
        feed.ingest_message(
            {"type": "price_update", "price_feed": {"id": FEED_ID}}
        )


def test_ingest_malformed_price_fields_raise():
    feed, _ = _make_feed()
    with pytest.raises(MalformedPythMessageError):
        feed.ingest_message(
            {
                "type": "price_update",
                "price_feed": {
                    "id": FEED_ID,
                    "price": {"price": "not_a_number", "expo": -8, "publish_time": 1},
                },
            }
        )


def test_ingest_bare_hex_id_without_0x_prefix_normalizes():
    feed, store = _make_feed()
    bare = FEED_ID[2:]
    msg = {
        "type": "price_update",
        "price_feed": {
            "id": bare,
            "price": {
                "price": "8000000000",
                "conf": "0",
                "expo": -8,
                "publish_time": 1745000001,
                "num_publishers": 5,
            },
        },
    }
    commodity, _ = feed.ingest_message(msg)
    assert commodity == "wti"
    assert store.latest("wti").price == pytest.approx(80.0)
