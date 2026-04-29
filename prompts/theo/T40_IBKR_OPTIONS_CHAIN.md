# Phase T-40 — IBKR Options Chain Ingest

## Premise
Read `prompts/build/PREMISE.md` and `CLAUDE.md`.

## Prerequisites
- IBKR margin account is active.
- CME agricultural market data subscription is active (~$10/mo).
- IB Gateway is installed, running, and accepting API connections.

## Context
The CME public endpoint is blocked (anti-scraping). IBKR provides the same
data via their API — full ZS options chain with strikes, prices, IVs, and
greeks. This is the data the full RND pipeline (`engine/rnd/pipeline.py`)
was built to consume.

## Outputs
- `feeds/ibkr/options_chain.py` — pull ZS options chain via ib_insync:
  - Connect to IB Gateway.
  - Request option chain for ZS front-month.
  - Parse into `OptionsChain` dataclass (same format as `feeds/cme/options_chain.py`).
  - Cache with configurable TTL (default 15 min).
  - Handles: connection errors, no data, partial chains.
- `feeds/ibkr/__init__.py`
- Updated `deploy/main.py` — option to use IBKR chain instead of synthetic.
- `tests/test_ibkr_options.py` — tests with mocked IB responses.

## Success criteria
- Pulls complete ZS options chain (50+ strikes with prices and IVs).
- Returns `OptionsChain` compatible with `engine/rnd/pipeline.compute_rnd()`.
- Handles IB Gateway disconnection gracefully (fall back to synthetic).
- Cache prevents excessive API calls.
- All existing tests pass.

## Key notes
- Use `ib_insync` (already installed).
- IB Gateway paper trading port: 4002. Live: 4001.
- ZS options: symbol="ZS", exchange="CBOT", secType="FOP".
- Use `ib.reqSecDefOptParams()` to get available expirations/strikes.
- Use `ib.reqMktData()` or `ib.reqTickers()` to get prices.
- This is I/O code — asyncio is appropriate here.
