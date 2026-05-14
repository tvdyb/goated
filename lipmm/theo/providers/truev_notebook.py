"""TruEV notebook — per-component anchor + delta breakdown for the dashboard.

Implements the `TheoNotebook` protocol. Renders a self-contained HTML
fragment showing:

  - Anchor date + index value
  - Per-component table (weight, anchor price, current price, Δ%, Δpts)
  - Implied basket level + delta from anchor
  - Forward-source freshness chip + per-row stale flag

The notebook reads the provider's internal forward source for live
component prices (already polled in the background by the provider's
own poll loop). No new I/O.
"""
from __future__ import annotations

import html
import time
from typing import TYPE_CHECKING

from lipmm.theo.providers._truev_index import reconstruct_index

if TYPE_CHECKING:
    from lipmm.theo.providers.truev import TruEVTheoProvider


# Per-component metadata for display. Keys match the symbols in
# TruEvWeights / TruEvAnchor. Order is the display order in the table.
_LABEL_UNIT: list[tuple[str, str, str]] = [
    ("HG=F",       "Copper",    "$/lb"),
    ("NICKEL_TE",  "Nickel",    "$/T"),
    ("COBALT_TE",  "Cobalt",    "$/T"),
    ("PA=F",       "Palladium", "$/oz"),
    ("LITHIUM_TE", "Lithium",   "CNY/T"),
    ("PL=F",       "Platinum",  "$/oz"),
]

# A component price is "stale" if its cached fetched_at_ts is older
# than this many seconds. Forward source polls every 120s by default;
# 300s allows for one missed cycle without crying wolf.
_STALE_THRESHOLD_S = 300.0


def _fmt_price(sym: str, value: float) -> str:
    """Format a price for the symbol's natural precision."""
    if sym in ("LITHIUM_TE", "COBALT_TE", "NICKEL_TE"):
        return f"{value:,.0f}"
    if sym == "NICK.L":  # legacy backtest path
        return f"{value:.4f}"
    if sym in ("PA=F", "PL=F"):
        return f"{value:,.2f}"
    return f"{value:.4f}"  # HG=F


def _fmt_pct(pct: float) -> str:
    return f"{pct:+.3f}%"


def _fmt_pts(pts: float) -> str:
    return f"{pts:+.2f}"


def _row_color(pct: float) -> str:
    if pct > 0:
        return "var(--yes, #4ade80)"
    if pct < 0:
        return "var(--no, #f87171)"
    return "var(--ink-lo, #9aa0a6)"


class TruEVNotebook:
    """Component anchor + delta breakdown for the TruEV theo provider.

    The notebook reads live state from the provider's forward source
    each render — no I/O, just in-memory cache lookups.
    """

    key = "truev"
    label = "TruEV basket"

    def __init__(self, provider: TruEVTheoProvider) -> None:
        self._provider = provider

    async def render(self) -> str:
        cfg = self._provider._cfg
        anchor = cfg.anchor
        weights = cfg.weights.weights
        forward = self._provider._forward

        # In-memory snapshots — never blocks.
        prices_ts = forward.latest_prices()
        now = time.time()
        oldest_age_s = forward.oldest_age_seconds(now=now)

        # Anchor staleness: compare the anchor's date to today's UTC
        # date. The anchor's MEANING is "yesterday's Truflation EOD
        # print," so during normal day-N trading the anchor should be
        # dated day-(N-1). Warn only when we've missed a re-anchor
        # cycle (anchor is 2+ days behind today's UTC date).
        anchor_age_warn_html = ""
        try:
            from datetime import datetime, timezone
            anchor_dt = datetime.strptime(anchor.anchor_date, "%Y-%m-%d")
            anchor_date_utc = anchor_dt.date()
            today_utc = datetime.fromtimestamp(now, tz=timezone.utc).date()
            days_behind = (today_utc - anchor_date_utc).days
            if days_behind >= 2:
                anchor_age_warn_html = (
                    f'<span style="color: var(--no, #f87171); margin-left: 8px;">'
                    f'⚠ anchor is {days_behind}d behind today — re-anchor missed</span>'
                )
        except Exception:
            pass

        # Build per-component rows. Each row computes Δ%, Δpts using
        # the same anchored-multiplicative formula the runner uses.
        rows_html: list[str] = []
        current_prices: dict[str, float] = {}
        for sym, label, unit in _LABEL_UNIT:
            if sym not in weights or sym not in anchor.anchor_prices:
                continue
            w = float(weights[sym])
            p_anchor = float(anchor.anchor_prices[sym])
            tup = prices_ts.get(sym)
            if tup is None:
                # Missing entirely — show placeholder
                rows_html.append(
                    f'<tr>'
                    f'<td style="padding:4px 8px;">{html.escape(label)}</td>'
                    f'<td style="padding:4px 8px; color: var(--ink-lo);">{unit}</td>'
                    f'<td style="padding:4px 8px; text-align:right; font-variant-numeric: tabular-nums;">{w*100:.2f}%</td>'
                    f'<td style="padding:4px 8px; text-align:right; font-variant-numeric: tabular-nums;">{_fmt_price(sym, p_anchor)}</td>'
                    f'<td style="padding:4px 8px; text-align:right; color: var(--no, #f87171);">missing</td>'
                    f'<td style="padding:4px 8px; text-align:right; color: var(--ink-lo);">—</td>'
                    f'<td style="padding:4px 8px; text-align:right; color: var(--ink-lo);">—</td>'
                    f'</tr>'
                )
                continue
            p_now, fetched_at = tup
            current_prices[sym] = p_now
            pct = (p_now / p_anchor - 1.0) * 100.0
            contrib = anchor.anchor_index_value * w * (p_now / p_anchor - 1.0)
            age = now - fetched_at
            stale_flag = (
                f' <span title="last update {age:.0f}s ago" '
                f'style="color: var(--no, #f87171); font-size: 9px;">●</span>'
                if age > _STALE_THRESHOLD_S else ""
            )
            color = _row_color(pct)
            rows_html.append(
                f'<tr>'
                f'<td style="padding:4px 8px;">{html.escape(label)}{stale_flag}</td>'
                f'<td style="padding:4px 8px; color: var(--ink-lo); font-size: 10px;">{unit}</td>'
                f'<td style="padding:4px 8px; text-align:right; font-variant-numeric: tabular-nums;">{w*100:.2f}%</td>'
                f'<td style="padding:4px 8px; text-align:right; font-variant-numeric: tabular-nums;">{_fmt_price(sym, p_anchor)}</td>'
                f'<td style="padding:4px 8px; text-align:right; font-variant-numeric: tabular-nums;">{_fmt_price(sym, p_now)}</td>'
                f'<td style="padding:4px 8px; text-align:right; color:{color}; font-variant-numeric: tabular-nums;">{_fmt_pct(pct)}</td>'
                f'<td style="padding:4px 8px; text-align:right; color:{color}; font-variant-numeric: tabular-nums;">{_fmt_pts(contrib)}</td>'
                f'</tr>'
            )

        # Implied basket level — only if we have ALL modeled symbols.
        modeled = set(weights.keys())
        implied_html: str
        if modeled.issubset(set(current_prices.keys())):
            try:
                implied = reconstruct_index(current_prices, cfg.weights, anchor)
                delta_pts = implied - anchor.anchor_index_value
                delta_pct = (implied / anchor.anchor_index_value - 1.0) * 100.0
                delta_color = _row_color(delta_pct)
                implied_html = (
                    f'<div style="margin-top: 10px; padding-top: 8px; '
                    f'border-top: 1px solid var(--border, #2a2e34); '
                    f'display: flex; gap: 16px; align-items: baseline;">'
                    f'<span style="color: var(--ink-lo); font-size: 10px; '
                    f'text-transform: uppercase; letter-spacing: 0.04em;">Implied basket</span>'
                    f'<span style="font-size: 16px; font-variant-numeric: tabular-nums; '
                    f'color: var(--ink-hi);">{implied:.2f}</span>'
                    f'<span style="color: {delta_color}; font-variant-numeric: tabular-nums;">'
                    f'{_fmt_pts(delta_pts)} pts</span>'
                    f'<span style="color: {delta_color}; font-variant-numeric: tabular-nums;">'
                    f'({_fmt_pct(delta_pct)})</span>'
                    f'</div>'
                )
            except Exception as exc:
                implied_html = (
                    f'<div style="margin-top: 10px; color: var(--no, #f87171); '
                    f'font-size: 11px;">reconstruction failed: {html.escape(str(exc))}</div>'
                )
        else:
            missing = sorted(modeled - set(current_prices.keys()))
            implied_html = (
                f'<div style="margin-top: 10px; color: var(--no, #f87171); '
                f'font-size: 11px;">implied basket unavailable — missing: '
                f'{", ".join(html.escape(s) for s in missing)}</div>'
            )

        # Forward-source freshness chip
        if oldest_age_s == float("inf"):
            freshness_html = (
                '<span style="color: var(--no, #f87171); margin-left: 8px; font-size: 10px;">'
                'no forward data yet</span>'
            )
        else:
            color = "var(--ink-lo)" if oldest_age_s < _STALE_THRESHOLD_S else "var(--no, #f87171)"
            freshness_html = (
                f'<span style="color: {color}; margin-left: 8px; font-size: 10px;">'
                f'oldest source: {oldest_age_s:.0f}s ago</span>'
            )

        # Header
        header_html = (
            f'<div style="display: flex; align-items: baseline; gap: 12px; '
            f'margin-bottom: 8px;">'
            f'<span style="color: var(--ink-lo); font-size: 10px; '
            f'text-transform: uppercase; letter-spacing: 0.04em;">Anchor</span>'
            f'<span style="font-size: 14px; font-variant-numeric: tabular-nums; '
            f'color: var(--ink-hi);">{html.escape(anchor.anchor_date)}</span>'
            f'<span style="font-size: 14px; font-variant-numeric: tabular-nums; '
            f'color: var(--ink-hi);">→ {anchor.anchor_index_value:.2f}</span>'
            f'{anchor_age_warn_html}{freshness_html}'
            f'</div>'
        )

        # Table
        table_html = (
            '<table style="width: 100%; border-collapse: collapse; '
            'font-family: \'JetBrains Mono\', ui-monospace, monospace; '
            'font-size: 11px;">'
            '<thead>'
            '<tr style="border-bottom: 1px solid var(--border, #2a2e34); '
            'color: var(--ink-lo); text-transform: uppercase; '
            'letter-spacing: 0.04em; font-size: 9px;">'
            '<th style="padding:4px 8px; text-align:left;">Component</th>'
            '<th style="padding:4px 8px; text-align:left;">Unit</th>'
            '<th style="padding:4px 8px; text-align:right;">Weight</th>'
            '<th style="padding:4px 8px; text-align:right;">Anchor</th>'
            '<th style="padding:4px 8px; text-align:right;">Now</th>'
            '<th style="padding:4px 8px; text-align:right;">Δ %</th>'
            '<th style="padding:4px 8px; text-align:right;">Δ pts</th>'
            '</tr></thead><tbody>'
            + "".join(rows_html) +
            '</tbody></table>'
        )

        return header_html + table_html + implied_html
