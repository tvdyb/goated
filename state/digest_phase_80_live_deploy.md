# Digest: Phase 80 — Live Small Deployment

**Date:** 2026-04-28
**Status:** COMPLETE

---

## Summary

Phase 80 wires all Phase 50-75 components into a deployable single-process market maker. The system runs a 30-second periodic loop: CME ingest -> RND pipeline -> quoter -> Kalshi order submission -> position tracking -> risk monitoring -> hedge trigger -> IB hedge execution.

---

## Deliverables

| Deliverable | Lines | Tests |
|---|---|---|
| `deploy/main.py` | ~520 | 30 integration tests |
| `deploy/config.yaml` | 50 | config loading tests |
| `attribution/pnl.py` | ~200 | 3 PnL tests |
| `deploy/README.md` | ~160 | (operational runbook) |
| `tests/test_integration.py` | ~450 | 30 tests total |

**Total tests:** 848 (30 new, up from 818).

---

## Key design decisions

1. **Capital cap: $1,000** — enforced via RiskLimits.max_loss_cents = 100,000c.
2. **KXSOYBEANMON only** — single series for initial deployment.
3. **post_only=True** on every order — non-negotiable.
4. **Kill switch: 3 triggers** — risk breach, IB disconnect+delta, PnL drawdown.
5. **Graceful shutdown** — SIGINT/SIGTERM cancels all resting orders.
6. **Secrets via env vars** — KALSHI_API_KEY, KALSHI_PRIVATE_KEY_PATH.

---

## Before going live

See `state/action_live_deploy/handoff.md` for full pre-flight checklist.

Critical: paper-trade for 1 week before any real capital.

---

## What's next

- Phase 85: Multi-series support (KXCORNMON)
- Phase 90: WS integration for real-time fills
- Phase 95: DuckDB PnL store, dashboard
- Phase 100: Production hardening (logging, alerting, monitoring)
