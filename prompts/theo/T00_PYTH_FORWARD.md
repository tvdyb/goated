# Phase T-00 — Wire Pyth Real-Time Forward Price

## Premise (ALWAYS READ FIRST)
Read `prompts/build/PREMISE.md` and `CLAUDE.md`. If either does not exist, halt.

## Context
The market maker is LIVE on Kalshi KXSOYBEANMON. Currently, the forward price
for the synthetic GBM theo is **guessed from Kalshi quotes** (finding the strike
where Yes bid/ask straddles 50c). This is inaccurate — Kalshi quotes are wide,
stale, and reflect prediction-market bias, not the actual soybean futures price.

Pyth Network provides real-time ZS soybean futures prices via their Hermes API.
The feed ID is already configured in `config/pyth_feeds.yaml`. We just need to
wire it into the live system.

## Inputs
1. `config/pyth_feeds.yaml` — Pyth feed configuration (feed ID, staleness thresholds).
2. `deploy/lip_mode.py` — LIP-optimized market maker (uses `self._forward_estimate`).
3. `deploy/main.py` — Spread-capture market maker (also uses `self._forward_estimate`).
4. `feeds/` — existing feed infrastructure.
5. Pyth Hermes API docs: `https://hermes.pyth.network/docs/`

## Outputs
- `feeds/pyth/client.py` — Async Pyth Hermes REST client that pulls latest ZS price.
- `feeds/pyth/forward.py` — Forward price provider that:
  - Pulls price every N seconds (configurable, default 5s).
  - Returns price in $/bushel (e.g. 11.77).
  - Validates staleness (reject if older than threshold from `pyth_feeds.yaml`).
  - Falls back to Kalshi-inferred forward if Pyth is unavailable.
- Updated `deploy/lip_mode.py` — uses Pyth forward instead of Kalshi-inferred.
- Updated `deploy/main.py` — same.
- `tests/test_pyth_forward.py` — tests with mocked Pyth responses.

## Success criteria
- Pyth forward updates every 5 seconds with real ZS price.
- Forward is within 1c of CME ZS mid (Pyth tracks CME closely).
- Staleness check rejects prices older than `pyth_max_staleness_ms` from config.
- Fallback to Kalshi-inferred forward works when Pyth is down.
- All existing tests still pass.
- The synthetic GBM theo now uses a real futures price, not a guess.

## Key implementation notes
- Pyth Hermes is a simple REST API: `GET /v2/updates/price/latest?ids[]={feed_id}`
- Response includes `price`, `conf` (confidence interval), `publish_time`.
- Price is in a fixed-point format: `price * 10^expo`. Parse carefully.
- The feed ID for ZS soybeans is in `config/pyth_feeds.yaml` under `soy.pyth_feed_id`.
- Do NOT use WebSocket for MVP — REST polling every 5s is sufficient and simpler.
- Non-negotiables: no pandas, fail-loud on stale data, asyncio for I/O only.

## Handoff
- Write `state/action_theo_t00/handoff.md` with what was done.
- Update `CLAUDE.md` module status to reflect Pyth forward is wired.
