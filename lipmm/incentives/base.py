"""IncentiveProgram dataclass + IncentiveProvider Protocol.

The dataclass mirrors Kalshi's `/incentive_programs` row shape with a
couple of convenience properties so the dashboard renderer doesn't need
to do unit conversion or date math inline. The protocol is intentionally
minimal — `async list_active() -> list[IncentiveProgram]` — so future
exchanges (Polymarket etc.) can plug in without lipmm changes.

Unit conventions worth memorizing:

  - `period_reward` is in **centi-cents** (1/10000 of a dollar) per the
    Kalshi spec. Divide by 10_000 for dollars.
  - `discount_factor_bps` is basis points (1 bps = 0.01%). Divide by
    10_000 for fraction.
  - `target_size_fp` is a **fixed-point string** like "100.00" — parsed
    to `target_size_contracts: float`. May be None for some programs.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class IncentiveProgram:
    """One liquidity- or volume-incentive program from Kalshi.

    All API fields are preserved verbatim under their original names;
    convenience properties layer on top for operator-friendly display.
    """

    id: str
    market_id: str
    market_ticker: str
    incentive_type: str       # "liquidity" or "volume"
    incentive_description: str
    start_date_ts: float      # unix timestamp (parsed from ISO-8601 start_date)
    end_date_ts: float        # unix timestamp (parsed from ISO-8601 end_date)
    period_reward_centi_cents: int
    paid_out: bool
    discount_factor_bps: int | None = None
    target_size_fp: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    # ── Convenience accessors ─────────────────────────────────────

    @property
    def period_reward_dollars(self) -> float:
        """Period reward in dollars. Kalshi's `period_reward` is in
        centi-cents (1/10000 of a dollar)."""
        return self.period_reward_centi_cents / 10_000.0

    @property
    def discount_factor_pct(self) -> float | None:
        """Discount factor as a percentage (0..100). None if absent."""
        if self.discount_factor_bps is None:
            return None
        return self.discount_factor_bps / 100.0

    @property
    def target_size_contracts(self) -> float | None:
        """Target size as float contracts. None if absent."""
        if self.target_size_fp is None:
            return None
        try:
            return float(self.target_size_fp)
        except (TypeError, ValueError):
            return None

    def time_remaining_s(self, now_ts: float | None = None) -> float:
        """Seconds until end_date. Negative if already past."""
        t = now_ts if now_ts is not None else time.time()
        return self.end_date_ts - t

    def is_active(self, now_ts: float | None = None) -> bool:
        """True iff `now_ts` is between start_date and end_date AND the
        program isn't marked paid_out."""
        t = now_ts if now_ts is not None else time.time()
        return (
            (not self.paid_out)
            and self.start_date_ts <= t <= self.end_date_ts
        )

    # ── Parser ─────────────────────────────────────────────────────

    @classmethod
    def from_api(cls, entry: dict[str, Any]) -> "IncentiveProgram":
        """Build from one element of the `incentive_programs` array."""
        return cls(
            id=str(entry["id"]),
            market_id=str(entry["market_id"]),
            market_ticker=str(entry["market_ticker"]),
            incentive_type=str(entry["incentive_type"]),
            incentive_description=str(entry.get("incentive_description", "")),
            start_date_ts=_parse_iso8601_ts(entry["start_date"]),
            end_date_ts=_parse_iso8601_ts(entry["end_date"]),
            period_reward_centi_cents=int(entry["period_reward"]),
            paid_out=bool(entry.get("paid_out", False)),
            discount_factor_bps=(
                int(entry["discount_factor_bps"])
                if entry.get("discount_factor_bps") is not None else None
            ),
            target_size_fp=(
                str(entry["target_size_fp"])
                if entry.get("target_size_fp") is not None else None
            ),
            raw=dict(entry),
        )

    def to_dict(self) -> dict[str, Any]:
        """Operator-friendly dict for the dashboard / API response."""
        return {
            "id": self.id,
            "market_id": self.market_id,
            "market_ticker": self.market_ticker,
            "incentive_type": self.incentive_type,
            "incentive_description": self.incentive_description,
            "start_date_ts": self.start_date_ts,
            "end_date_ts": self.end_date_ts,
            "period_reward_dollars": self.period_reward_dollars,
            "discount_factor_bps": self.discount_factor_bps,
            "discount_factor_pct": self.discount_factor_pct,
            "target_size_contracts": self.target_size_contracts,
            "paid_out": self.paid_out,
        }


def _parse_iso8601_ts(s: str) -> float:
    """Parse an ISO-8601 datetime string to a unix timestamp.

    Accepts the standard variants Kalshi returns: 'Z' suffix or
    explicit `+00:00`. Raises ValueError on unparseable input.
    """
    if not isinstance(s, str):
        raise ValueError(f"expected ISO-8601 string, got {type(s).__name__}")
    cleaned = s.replace("Z", "+00:00")
    dt = datetime.fromisoformat(cleaned)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


@runtime_checkable
class IncentiveProvider(Protocol):
    """Anything that can list currently-active incentive programs.

    Implementations decide their own caching policy; the lipmm
    `IncentiveCache` wraps any provider with periodic refresh +
    fault-tolerant snapshotting.
    """

    async def list_active(self) -> list[IncentiveProgram]:
        """Return all programs currently marked active.

        Should hit only one logical "fetch" per call; pagination is the
        provider's responsibility. May raise on transport failures —
        the caller (typically `IncentiveCache`) absorbs.
        """
        ...
