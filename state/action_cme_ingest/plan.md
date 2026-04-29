# F4-ACT-02 — CME Options Chain Ingest — Implementation Plan

**Action.** F4-ACT-02
**Type.** feature | **Effort.** L
**Gaps closed.** GAP-046 (CME ZS option-chain ingest), GAP-047 (put-call parity prune), GAP-063 (CME EOD settlements pull)

## Decision: CME data source (OD-37)

**Chosen source:** CME Group public delayed settlement data (free, no account needed).

**Rationale:**
- CME Group publishes EOD settlement data at public endpoints (cmegroup.com/CmeWS/mvc/Settlements/).
- Free, no API key required, structured JSON response.
- Sufficient for EOD chain data needs (front 3 expiries, all listed strikes).
- IB API historical options (OD-37 default) available as fallback but requires IB Gateway running.
- No Databento needed (MBP/MBO depth reconstruction not required for EOD chain).

**Fallback path:** IB API historical options via `ib_insync` if CME public endpoint becomes unreliable or rate-limited.

## Deliverables

1. `feeds/cme/__init__.py` — package docstring
2. `feeds/cme/errors.py` — `CMEIngestError`, `CMEChainError`, `CMESettleError`, `CMEParityError`
3. `feeds/cme/expiry_calendar.py` — CBOT options expiry calendar (ZS, ZC)
4. `feeds/cme/futures_settle.py` — daily settlement price puller
5. `feeds/cme/options_chain.py` — EOD options chain puller with put-call parity check
6. `tests/test_cme_ingest.py` — 37 tests

## Architecture

- All HTTP I/O is async via `httpx.AsyncClient` (asyncio for I/O only per non-negotiables).
- Data returned as numpy arrays (no pandas per non-negotiables).
- Fail-loud: `CMEIngestError` hierarchy, never return partial data.
- Put-call parity check (GAP-047): vectorized numpy, raises `CMEParityError` if >25% of strikes violate.
- Optional local cache (npz for chains, text for settle prices).
- Expiry calendar uses existing CBOT holiday set from `engine.event_calendar`.

## Verification criteria

- [x] `pull_options_chain` returns valid `OptionsChain` for mock data (3+ strikes, sorted, all fields populated).
- [x] Put-call parity check passes on clean synthetic data, raises on >25% violations, returns indices for minor violations.
- [x] `pull_settle` extracts front-month settlement price from mock CME JSON.
- [x] Expiry calendar produces correct dates for ZS/ZC 2026 (all Fridays, before FND).
- [x] `CMEIngestError` raised on HTTP failure, missing data, parse errors.
- [x] All 37 tests pass.
- [x] Ruff lint clean.
- [x] No existing tests broken (674 total pass).
