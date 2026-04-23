"""Pyth Hermes websocket ingestion.

Hermes is the public streaming endpoint for Pyth aggregate prices. One
client subscribes to N feed IDs; each `price_update` message carries the
aggregate price, confidence, publish time, and the count of publishers
that contributed to the aggregate.

Per-publisher gaming detection (spec "Things I care about" item 7) lives
at the Pythnet/Solana RPC level, not Hermes. That surface is added later;
this deliverable only consumes the aggregate but exposes `num_publishers`
to the tick store so the pricer can enforce `pyth_min_publishers`.

Failure modes the feed raises on (never silently swallows):
  * connection failure after retry budget
  * subscribed-feed message for an unknown feed id
  * malformed message (missing price or publish_time)

`ingest_message` is public so tests can exercise parsing with synthetic
payloads without opening a socket.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field

from state.tick_store import TickStore

log = logging.getLogger("goated.feeds.pyth")


class PythFeedError(RuntimeError):
    pass


class UnknownFeedError(PythFeedError):
    pass


class MalformedPythMessageError(PythFeedError):
    pass


@dataclass
class PythHermesFeed:
    endpoint: str
    feed_id_to_commodity: dict[str, str]
    tick_store: TickStore
    reconnect_backoff_s: float = 1.0
    max_reconnects: int = 5
    _subscribed: list[str] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        self._subscribed = sorted(self.feed_id_to_commodity)
        for commodity in self.feed_id_to_commodity.values():
            self.tick_store.register(commodity)

    def ingest_message(self, msg: dict) -> tuple[str, int] | None:
        """Parse one Hermes message; push on price updates. Returns
        `(commodity, seq)` on success, `None` if not a price update.

        Hermes wire format (price_update):
            {
              "type": "price_update",
              "price_feed": {
                "id": "<hex feed id>",
                "price": {
                  "price": "<string int>",
                  "conf": "<string int>",
                  "expo": <int>,
                  "publish_time": <unix seconds>,
                  "num_publishers": <int>      # when available
                }
              }
            }
        """
        if not isinstance(msg, dict):
            raise MalformedPythMessageError(f"expected dict, got {type(msg).__name__}")
        if msg.get("type") != "price_update":
            return None

        feed = msg.get("price_feed")
        if not isinstance(feed, dict):
            raise MalformedPythMessageError("price_update missing 'price_feed'")
        feed_id = feed.get("id")
        if not isinstance(feed_id, str):
            raise MalformedPythMessageError("price_feed missing string 'id'")

        # Hermes reports ids without the 0x prefix in some paths. Normalize.
        normalized = feed_id if feed_id.startswith("0x") else "0x" + feed_id
        commodity = self.feed_id_to_commodity.get(normalized) or self.feed_id_to_commodity.get(
            feed_id
        )
        if commodity is None:
            raise UnknownFeedError(f"feed id {feed_id} not in subscription table")

        price_block = feed.get("price")
        if not isinstance(price_block, dict):
            raise MalformedPythMessageError(f"{commodity}: price_feed missing 'price' block")

        try:
            raw_price = int(price_block["price"])
            expo = int(price_block["expo"])
            publish_time = int(price_block["publish_time"])
        except (KeyError, TypeError, ValueError) as exc:
            raise MalformedPythMessageError(f"{commodity}: malformed price fields: {exc}") from exc

        price = raw_price * (10.0**expo)
        ts_ns = publish_time * 1_000_000_000
        # Hermes currently surfaces publisher count inconsistently; default to 0
        # (which enforces min-publishers to be 0 for test feeds) and let the
        # pricer's pyth_min_publishers gate reject anything below threshold.
        num_publishers = int(price_block.get("num_publishers", 0))

        seq = self.tick_store.push(commodity, ts_ns, price, num_publishers)
        return commodity, seq

    async def run(self) -> None:
        """Connect to Hermes and stream. Reconnects up to `max_reconnects`
        times on transient errors before raising — no silent disconnection."""
        import websockets  # imported lazily so tests don't need the dep

        attempt = 0
        while True:
            try:
                async with websockets.connect(self.endpoint) as ws:
                    attempt = 0
                    await ws.send(json.dumps({"type": "subscribe", "ids": self._subscribed}))
                    log.info("pyth.connected endpoint=%s feeds=%d", self.endpoint, len(self._subscribed))
                    async for raw in ws:
                        try:
                            msg = json.loads(raw)
                        except json.JSONDecodeError as exc:
                            raise MalformedPythMessageError(f"non-JSON frame: {exc}") from exc
                        self.ingest_message(msg)
            except (OSError, asyncio.TimeoutError) as exc:
                attempt += 1
                if attempt > self.max_reconnects:
                    raise PythFeedError(
                        f"pyth hermes unreachable after {attempt} attempts: {exc}"
                    ) from exc
                log.warning("pyth.reconnect attempt=%d err=%s", attempt, exc)
                await asyncio.sleep(self.reconnect_backoff_s * attempt)
