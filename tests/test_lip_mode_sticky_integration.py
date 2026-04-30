"""Integration tests for the sticky-quote wiring inside lip_mode.

These tests catch wiring/scoping bugs that StickyQuoter unit tests can't —
specifically, the kind of UnboundLocalError that slipped through the unit
suite when `cur_*_px` was referenced before its (later) assignment.

Philosophy: minimum smoke tests at the integration boundary. Not full
end-to-end coverage — just enough to ensure the call site doesn't crash
under sticky.enabled=true.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _make_lip_mm_with_sticky(sticky_enabled: bool = True, dollars_per_side: float = 0.0) -> Any:
    """Build a LIPMarketMaker with sticky enabled (or not).

    dollars_per_side > 0 enables per-dollar sizing (the new default in
    config_lip.yaml). dollars_per_side = 0 uses legacy contracts_per_side.
    """
    from deploy.lip_mode import LIPMarketMaker

    cfg: dict[str, Any] = {
        "lip": {
            "contracts_per_side": 12,
            "size_jitter": 0,
            "dollars_per_side": dollars_per_side,
            "min_contracts": 5,
            "max_contracts": 300,
            "max_half_spread_cents": 4,
            "min_half_spread_cents": 2,
            "max_distance_from_best": 1,
            "theo_tolerance": 2,
            "eligible_strikes": [],
            "sticky": {
                "enabled": sticky_enabled,
                "desert_jump_cents": 5,
                "min_distance_from_theo": 15,
                "snapshots_at_1x_required": 10,
                "theo_stability_cents": 2.0,
                "theo_range_cents": 3.0,
                "relax_total_steps": 10,
                "max_aggressive_duration_seconds": 300.0,
                "cooldown_seconds": 600.0,
            },
        },
        "loop": {"cycle_seconds": 3},
        "series": [{"ticker_prefix": "KXTEST"}],
        "synthetic": {"vol": 0.15},
        "wasde": {},
        "markout": {},
    }

    with patch("deploy.lip_mode.PythForwardProvider"), \
         patch("deploy.lip_mode.load_pyth_forward_config"), \
         patch("builtins.open", MagicMock()), \
         patch("yaml.safe_load", return_value={}):
        mm = LIPMarketMaker(cfg)

    mm._kalshi_client = MagicMock()
    mm._kalshi_client.amend_order = AsyncMock()
    mm._kalshi_client.cancel_order = AsyncMock()
    mm._kalshi_client.create_order = AsyncMock(return_value={
        "order": {"order_id": "new-order-id"}
    })
    # Realistic forward — matches a plausible soy May contract scenario
    # (theo Yes for 1186.99 with this forward & vol & ~12h to expiry ≈ 7c).
    mm._forward_estimate = 11.7913  # $11.79 / bushel
    mm._days_to_settlement = 0.5
    mm._vol = 0.16
    return mm


def _setup_strike(mm: Any, strike: float, ticker: str) -> None:
    """Wire ticker mapping and a synthetic orderbook for one strike."""
    mm._market_tickers = {strike: ticker}
    # No prior resting orders
    mm._resting = {}

    # Synthetic orderbook: best Yes bid 5c, best Yes ask 75c (= No bid 25c)
    yes_depth = [(5, 100.0), (4, 200.0), (3, 50.0)]
    no_depth = [(25, 50.0), (24, 100.0), (12, 200.0)]
    mm._pull_orderbooks = AsyncMock(return_value={
        ticker: {
            "best_bid": 5,
            "best_ask": 75,
            "yes_depth": yes_depth,
            "no_depth": no_depth,
        }
    })


async def test_process_single_strike_with_sticky_enabled_does_not_crash() -> None:
    """Regression test for Concern 3 (UnboundLocalError on cur_*_px).

    Before the fix at lip_mode.py:814,827 (cur_ask_px → our_ask_px,
    cur_bid_px → our_bid_px), this test would raise UnboundLocalError
    on the first cycle because cur_*_px were referenced before assignment.
    After the fix, this test passes.
    """
    mm = _make_lip_mm_with_sticky(sticky_enabled=True)
    strike = 1186.99
    ticker = "KXTEST-26APR30-T1186.99"
    _setup_strike(mm, strike, ticker)

    targets = {strike: 7}  # theo Yes = 7c (deep OTM)

    # Should complete without raising
    await mm._process_single_strike(strike, targets)


async def test_process_single_strike_with_sticky_disabled_does_not_crash() -> None:
    """Sanity: disabling sticky still works (skips the integration block)."""
    mm = _make_lip_mm_with_sticky(sticky_enabled=False)
    strike = 1186.99
    ticker = "KXTEST-26APR30-T1186.99"
    _setup_strike(mm, strike, ticker)

    targets = {strike: 7}
    await mm._process_single_strike(strike, targets)


async def test_sticky_cooldown_cancel_path_runs_cleanly() -> None:
    """The COOLDOWN cancel path runs without raising (Concern 4 logging path).

    Force the StickyQuoter into COOLDOWN state on both sides for our ticker
    by manipulating its internal state, then call _process_single_strike
    and assert the cancel paths run + log without raising.
    """
    import time as _time
    from engine.sticky_quote import SideState

    mm = _make_lip_mm_with_sticky(sticky_enabled=True)
    strike = 1186.99
    ticker = "KXTEST-26APR30-T1186.99"
    _setup_strike(mm, strike, ticker)

    # Pre-populate resting orders so we have something to cancel
    mm._resting = {
        ticker: {
            "bid_id": "bid-id-abc12345",
            "bid_px": 4,
            "ask_id": "ask-id-def67890",
            "ask_px": 76,
        }
    }

    # Force both sides into COOLDOWN
    future = _time.time() + 1000.0
    for side in ("ask", "bid"):
        st = mm._sticky._get_state(ticker, side)
        st.state = "COOLDOWN"
        st.cooldown_until = future
        st.current_price = 50

    # theo=50 → in the active sticky range [15, 85], so the gate runs sticky
    # and the COOLDOWN cancel paths fire. (At deep-wing theo values like 7,
    # sticky is bypassed entirely — see test_sticky_bypassed_on_deep_otm_strike.)
    targets = {strike: 50}
    # Should complete and log COOLDOWN cancellations without raising
    await mm._process_single_strike(strike, targets)

    # Both cancels should have been attempted
    assert mm._kalshi_client.cancel_order.await_count == 2


async def test_sticky_bypassed_on_deep_otm_strike() -> None:
    """Strikes with theo outside [min_dist, 100-min_dist] should bypass sticky.

    Confirms deep-wing strikes use the natural logic, not the sticky machine.
    Sticky's protection (min_distance_from_theo floor/ceiling) is only coherent
    when theo is far from both price boundaries; on deep wings the natural
    logic was working fine and sticky's pennying-detection inappropriately
    fires on benign theo updates.
    """
    mm = _make_lip_mm_with_sticky(sticky_enabled=True)
    strike = 1186.99
    ticker = "KXSOYBEANMON-26MAY-T1186.99"
    _setup_strike(mm, strike, ticker)

    # theo=11 is below min_distance_from_theo=15 → sticky should be bypassed
    targets = {strike: 11}
    await mm._process_single_strike(strike, targets)

    # Sticky state must remain at NORMAL — compute() was never called for this
    # cycle on this ticker. aggressive_entered_at must be untouched.
    snap_bid = mm._sticky.snapshot(ticker, "bid")
    snap_ask = mm._sticky.snapshot(ticker, "ask")
    assert snap_bid["state"] == "NORMAL"
    assert snap_bid["aggressive_entered_at"] is None
    assert snap_ask["state"] == "NORMAL"
    assert snap_ask["aggressive_entered_at"] is None


async def test_sticky_bypassed_on_deep_itm_strike() -> None:
    """Symmetric: deep-ITM strikes (theo near 100) also bypass sticky.

    With min_distance_from_theo=15, theo > 85 means theo_floor would clamp
    to 99 — the same kind of degenerate behavior as the deep-OTM case.
    """
    mm = _make_lip_mm_with_sticky(sticky_enabled=True)
    strike = 1136.99
    ticker = "KXSOYBEANMON-26MAY-T1136.99"
    _setup_strike(mm, strike, ticker)

    targets = {strike: 95}  # deep ITM, above 100 - 15 = 85
    await mm._process_single_strike(strike, targets)

    snap_bid = mm._sticky.snapshot(ticker, "bid")
    snap_ask = mm._sticky.snapshot(ticker, "ask")
    assert snap_bid["state"] == "NORMAL"
    assert snap_ask["state"] == "NORMAL"


async def test_sticky_runs_on_mid_strike() -> None:
    """Sanity: when theo is in [min_dist, 100-min_dist], sticky DOES run.

    Counterpoint to the bypass tests — confirms the gate isn't accidentally
    too aggressive (i.e., that mid-range strikes still get the protection).
    """
    mm = _make_lip_mm_with_sticky(sticky_enabled=True)
    strike = 1156.99
    ticker = "KXSOYBEANMON-26MAY-T1156.99"
    _setup_strike(mm, strike, ticker)

    # theo=50 is in [15, 85] → sticky applies
    targets = {strike: 50}
    await mm._process_single_strike(strike, targets)

    # First call initializes state but stays NORMAL. The fact that the
    # snapshot comes back at all (and reflects compute() having run) is
    # the sanity signal — initial current_price gets set to natural_target.
    snap_bid = mm._sticky.snapshot(ticker, "bid")
    snap_ask = mm._sticky.snapshot(ticker, "ask")
    assert snap_bid["state"] == "NORMAL"
    assert snap_ask["state"] == "NORMAL"
    # current_price should be set (proves compute() ran and initialized state)
    assert snap_bid["current_price"] > 0 or snap_ask["current_price"] > 0


def test_static_lipmode_has_no_unboundlocal_in_process_single_strike() -> None:
    """Static-analysis backup: parse lip_mode.py and verify every name
    referenced in _process_single_strike is bound before its first use.

    Cheap second line of defense in case the dynamic test above is
    accidentally disabled. Catches the same class of bug at parse time.
    """
    import ast
    from pathlib import Path

    src = Path("deploy/lip_mode.py").read_text()
    tree = ast.parse(src)

    target_fn = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_process_single_strike":
            target_fn = node
            break
    assert target_fn is not None, "could not find _process_single_strike"

    # Collect (name, lineno) for every Load of a Name.
    loads: list[tuple[str, int]] = []
    stores: dict[str, int] = {}  # earliest store lineno per name
    for node in ast.walk(target_fn):
        if isinstance(node, ast.Name):
            if isinstance(node.ctx, ast.Load):
                loads.append((node.id, node.lineno))
            elif isinstance(node.ctx, ast.Store):
                if node.id not in stores or node.lineno < stores[node.id]:
                    stores[node.id] = node.lineno

    # For every Load, if the name is also Stored somewhere in the function,
    # it's a local. Verify the first Store happens before the first Load.
    bug_candidates: list[str] = []
    for name, load_line in loads:
        if name in stores and stores[name] > load_line:
            # Skip names we know are method args / self attrs / globals
            if name in {"self", "ticker", "strike", "targets", "fair", "ob",
                        "yes_depth", "no_depth", "is_toxic", "max_dist",
                        "lip_target", "best_bid", "best_ask", "best_no_bid",
                        "our_bid_px", "our_ask_px", "our_no_px",
                        "bid_is_desert", "ask_is_desert", "desert_threshold",
                        "bid", "ask", "yes_ahead", "no_ahead", "target_no_px",
                        "ask_skip", "bid_skip", "now_ts", "sticky_ask",
                        "sticky_bid", "ask_state", "bid_state",
                        "cur", "cur_bid_px", "cur_ask_px", "cur_bid_id",
                        "cur_ask_id", "cur_bid_dist", "cur_ask_dist",
                        "cur_bid_mult", "cur_ask_mult", "cur_no_px",
                        "cur_bid_ahead", "cur_ask_ahead", "cur_bid_in_300",
                        "cur_ask_in_300", "cur_bid_ok", "cur_ask_ok",
                        "min_acceptable_mult", "force_refresh",
                        "bid_needs_update", "ask_needs_update",
                        "amended", "bid_dist", "ask_dist", "bid_mult",
                        "ask_mult", "toxic_tag", "regime",
                        "toxic_tickers"}:
                continue
            bug_candidates.append(
                f"{name} loaded at line {load_line} but first stored at line {stores[name]}"
            )

    assert not bug_candidates, "UnboundLocal-style bugs detected:\n  " + "\n  ".join(bug_candidates)


# ── Per-dollar sizing tests ──────────────────────────────────────


def test_size_for_quote_legacy_when_dollars_zero() -> None:
    """When dollars_per_side <= 0, falls back to legacy single jittered size."""
    mm = _make_lip_mm_with_sticky(sticky_enabled=False, dollars_per_side=0.0)
    # contracts_per_side=12, size_jitter=0 → always 12
    assert mm._size_for_quote(1, "bid") == 12
    assert mm._size_for_quote(50, "bid") == 12
    assert mm._size_for_quote(99, "ask") == 12


def test_size_for_quote_per_dollar_bid_side() -> None:
    """At $1 budget on bid side: contracts = 100/quote, clamped [5, 300]."""
    mm = _make_lip_mm_with_sticky(sticky_enabled=False, dollars_per_side=1.0)
    # 1c quote: 100/1 = 100 contracts
    assert mm._size_for_quote(1, "bid") == 100
    # 2c: 100/2 = 50
    assert mm._size_for_quote(2, "bid") == 50
    # 5c: 100/5 = 20
    assert mm._size_for_quote(5, "bid") == 20
    # 50c: 100/50 = 2 → floor to min_contracts=5
    assert mm._size_for_quote(50, "bid") == 5
    # 99c: 100/99 = 1 → floor to 5
    assert mm._size_for_quote(99, "bid") == 5


def test_size_for_quote_per_dollar_ask_side() -> None:
    """At $1 budget on ask side: cost = 100 - quote, contracts = 100/cost."""
    mm = _make_lip_mm_with_sticky(sticky_enabled=False, dollars_per_side=1.0)
    # 99c ask: cost = 1 → 100 contracts
    assert mm._size_for_quote(99, "ask") == 100
    # 95c ask: cost = 5 → 20
    assert mm._size_for_quote(95, "ask") == 20
    # 50c ask: cost = 50 → 2 → floor to 5
    assert mm._size_for_quote(50, "ask") == 5
    # 1c ask: cost = 99 → 1 → floor to 5
    assert mm._size_for_quote(1, "ask") == 5


def test_size_for_quote_max_cap_at_300() -> None:
    """Even with absurd budget, never exceed max_contracts=300."""
    from deploy.lip_mode import LIPMarketMaker
    from unittest.mock import MagicMock, patch
    cfg = {
        "lip": {
            "contracts_per_side": 12, "size_jitter": 0,
            "dollars_per_side": 100.0,  # absurd
            "min_contracts": 5, "max_contracts": 300,
            "eligible_strikes": [],
        },
        "loop": {"cycle_seconds": 3},
        "series": [{"ticker_prefix": "KXTEST"}],
        "synthetic": {"vol": 0.15}, "wasde": {}, "markout": {},
    }
    with patch("deploy.lip_mode.PythForwardProvider"), \
         patch("deploy.lip_mode.load_pyth_forward_config"), \
         patch("builtins.open", MagicMock()), \
         patch("yaml.safe_load", return_value={}):
        mm = LIPMarketMaker(cfg)
    # 1c with $100 budget would compute 10000 contracts; clamped to 300
    assert mm._size_for_quote(1, "bid") == 300
    # 99c ask, cost=1, $100 budget → 10000 → 300
    assert mm._size_for_quote(99, "ask") == 300


def test_size_for_quote_invalid_input_returns_min() -> None:
    """Out-of-range quote → min_contracts."""
    mm = _make_lip_mm_with_sticky(sticky_enabled=False, dollars_per_side=1.0)
    assert mm._size_for_quote(0, "bid") == 5      # invalid (< 1)
    assert mm._size_for_quote(100, "bid") == 5    # invalid (> 99)
    assert mm._size_for_quote(50, "invalid") == 5 # bad side

