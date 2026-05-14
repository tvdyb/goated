# Generic market-maker bot — distribution guide

This document specifies exactly which files to include in a generic,
shareable build of the lipmm market-making framework — a build that
contains the bot infrastructure but **none of the operator-specific
content** (TruEV model code, anchored data, predefined tickers, log
files, soy-era components).

A recipient should be able to clone this distribution, plug in their
own theo provider, and start trading on any Kalshi event with a 90-
second runbook.

---

## File inclusion rules

### ✅ Include — core framework (~unchanged)

The `lipmm/` package is the framework itself. Market-agnostic by
design.

```
lipmm/                         # Entire package
├── __init__.py
├── control/                   # Control plane (HTTP + WebSocket + dashboard)
│   ├── auth.py                # JWT bearer auth
│   ├── broadcaster.py         # WebSocket fan-out
│   ├── commands.py            # Pydantic request/response schemas
│   ├── server.py              # FastAPI app
│   ├── state.py               # ControlState (pauses, knobs, locks, ...)
│   └── web/                   # Dashboard (templates, static, renderer)
├── execution/                 # OrderManager + ExchangeClient + Kalshi adapter
├── exploit/                   # Exploit framework (optional but harmless)
├── incentives/                # LIP scoring (CFTC Appendix A)
├── observability/             # DecisionLogger + RetentionManager
│                              # + EarningsHistory + MarkoutTracker
├── quoting/                   # DefaultLIPQuoting + StickyDefenseQuoting
├── risk/                      # Risk gates
├── runner/                    # LIPRunner — main loop
└── theo/                      # TheoProvider Protocol + generic providers
    ├── base.py
    └── providers/
        ├── __init__.py        # (edit to drop TruEV re-exports)
        ├── _function.py       # function_provider decorator
        ├── file.py            # FilePollTheoProvider
        └── http.py            # HttpPollTheoProvider
```

### ✅ Include — Kalshi exchange integration

```
feeds/__init__.py
feeds/kalshi/
├── __init__.py
├── __main__.py
├── auth.py                    # KalshiAuth (reads env vars)
├── capture.py                 # WebSocket frame capture (optional dev tool)
├── client.py                  # KalshiClient (REST + RSA-PSS auth)
├── errors.py
├── events.py
```

**Note**: skip `feeds/kalshi/lip_pool.py` and
`feeds/kalshi/lip_score.py` — both are soy-era utilities not used by
the lipmm framework.

### ✅ Include — entry point + safe-default theo

```
deploy/
├── __init__.py
├── _stub_theo.py              # StubTheoProvider — safe by default
├── lipmm_run.py               # Main CLI entry — ⚠️ strip TruEV bits, see below
└── README_quickstart.md       # Runbook
```

**lipmm_run.py must be modified** (see "Genericization edits" below)
to remove the TruEV-specific `if prefix == "KXTRUEV":` block and the
`--truev-*` CLI flags. Otherwise the file is fully generic.

### ✅ Include — documentation

```
docs/
├── API.md                     # HTTP + WebSocket reference
├── DASHBOARD.md               # Dashboard UI reference
└── (this file — or rename to README_FRAMEWORK.md)
```

### ✅ Include — packaging + project metadata

```
pyproject.toml                 # Package manifest
README.md                      # Project overview (may want to rewrite)
.gitignore                     # Helpful baseline
```

### ✅ Include — relevant tests

Tests that exercise the framework, not market-specific code:

```
tests/
├── __init__.py
├── _bs_reference.py
├── conftest.py
├── test_amend.py
├── test_broadcaster.py
├── test_capture.py
├── test_control_*.py          # Control-plane tests
├── test_decision_logger.py
├── test_earnings_history.py
├── test_end_to_end.py
├── test_events.py
├── test_execution.py
├── test_exploit_state.py
├── test_gbm_analytical.py
├── test_incentives*.py
├── test_integration.py
├── test_kalshi_adapter.py
├── test_kalshi_client.py
├── test_kalshi_fees.py
├── test_kalshi_ws.py
├── test_kill.py
├── test_lip_viability.py
├── test_lipmm_run.py          # ⚠️ delete TruEV assertions
├── test_manual_orders.py
├── test_markout_lipmm.py      # the lipmm version, not soy
├── test_multi_event.py
├── test_operator_drawer.py
├── test_orderbook_broadcast.py
├── test_pnl_grid.py
├── test_quoting_protocol.py
├── test_renderer.py           # if exists
├── test_retention.py
├── test_risk_gates.py
├── test_runner*.py
├── test_strategy_*.py
├── test_strike_grid.py
├── test_theo_providers.py
├── test_websocket.py
```

---

## File exclusion rules

### ❌ Exclude — operator's TruEV model

These embed your model's calibration, weights, and anchors:

```
lipmm/theo/providers/truev.py
lipmm/theo/providers/_truev_index.py
feeds/truflation/               # entire directory
feeds/tradingeconomics/         # entire directory (only used by TruEV)
deploy/truev_backtest.py
deploy/truev_backtest_csv.py
deploy/truev_fit_weights.py
deploy/truev_reanchor.py
deploy/truev_smoke.py
ev_commodity_prices.csv         # your CSV
indexAndBasket.csv              # your CSV
tests/test_truev_*.py           # all truev-specific tests
```

### ❌ Exclude — soy-era (paused, stale)

```
engine/                         # soy theo stack
state/                          # soy position store
attribution/                    # soy PnL tracker
models/                         # soy models
validation/                     # soy sanity gates
calibration/                    # stub
hedge/                          # IBKR (unconfigured)
fees/                           # soy fee math
audit/                          # read-only refs
prompts/                        # soy prompts
analysis/                       # soy analysis
feeds/pyth/                     # soy data source
feeds/usda/                     # soy data source
feeds/weather/                  # soy data source
feeds/ibkr/                     # soy data source
feeds/cme/                      # soy data source
feeds/pyth_ws.py                # soy realtime
feeds/kalshi/lip_pool.py        # soy LIP DuckDB
feeds/kalshi/lip_score.py       # soy LIP score
deploy/lip_mode.py              # stale soy entry point
deploy/main.py                  # stale soy spread-capture
deploy/dashboard.py             # stale Flask dashboard
deploy/exploit_quick.py         # exploit framework's CLI helper (optional, see note)
deploy/config.yaml              # soy config
deploy/config_lip.yaml          # soy config
deploy/config_test.yaml         # soy config
deploy/README.md                # soy runbook
```

> **Note on `lipmm/exploit/`**: keep this — it's the new exploit
> framework, market-agnostic, and useful. Just skip `deploy/exploit_quick.py`
> which is a one-off CLI helper for soy.

### ❌ Exclude — personal data

```
logs/                           # decision logs, earnings history
screenshots/
Downloads/
BRLUSD-PROJ/
mm-setup-main/
data/
config/
ONBOARDING.md                   # soy-era onboarding
CLAUDE.md                       # operator's working notes (regenerate fresh)
.claude/                        # operator's local AI session state
=12.0                           # mystery file
```

### ❌ Exclude — soy-era tests

```
tests/test_cbot_settle.py
tests/test_cme_ingest.py
tests/test_corridor.py
tests/test_goldman_roll.py
tests/test_ibkr_hedge.py
tests/test_ibkr_options.py
tests/test_implied_vol.py
tests/test_lip_mode_sticky_integration.py
tests/test_lip_pool.py
tests/test_lip_score.py
tests/test_markout.py           # soy version; keep test_markout_lipmm.py
# … any test importing from engine/ / state/ / models/
```

### ❌ Exclude — build artifacts + caches

```
.benchmarks/
.pytest_cache/
.ruff_cache/
.venv/
.git/                           # recipient initializes their own
__pycache__/                    # any
*.egg-info/
goated.egg-info/
```

---

## Genericization edits

After copying the included files, two files need surgical edits to
remove TruEV-specific imports and CLI flags:

### `deploy/lipmm_run.py`

**Remove the entire `if prefix == "KXTRUEV":` block** (around lines
386-455). The remaining loop (registering `StubTheoProvider(prefix)`
for unknown prefixes) becomes the default for every event.

**Remove these CLI args** from the `argparse` setup (around lines
705-715):

```python
"--truev-settlement-iso"
"--truev-vol"
"--truev-max-confidence"
"--truev-anchor-date"
"--truev-anchor-index"
```

Recipients can re-add similar provider-specific flags when they wire
their own theo provider.

### `lipmm/theo/providers/__init__.py`

Remove the TruEV imports + `__all__` entries. After surgery the
file should re-export only:

```python
from lipmm.theo.providers._function import function_provider
from lipmm.theo.providers.file import FilePollTheoProvider
from lipmm.theo.providers.http import HttpPollTheoProvider

__all__ = [
    "FilePollTheoProvider",
    "HttpPollTheoProvider",
    "function_provider",
]
```

### `lipmm/control/state.py`

Remove the `truev_model_rmse_pts` entry from `knob_bounds`. Not
mandatory (it's a leaf knob that just becomes a no-op without the
TruEV provider), but cleaner.

### `lipmm/control/web/templates/partials/tab_knobs.html`

Remove the `truev_model_rmse_pts` row. Same rationale.

### `tests/test_lipmm_run.py`

Remove the test cases that assert TruEV behavior (if any reference
`TruEVTheoProvider` or KXTRUEV-specific behavior).

### `tests/test_operator_drawer.py`

The "expected partials" set check should still pass since the
dashboard partials are framework-level. Verify after build.

### `feeds/__init__.py`

Currently empty — keep as-is.

---

## What recipients add

To go from "framework skeleton" to "running bot on Kalshi event X",
the recipient needs to write **one file**: their theo provider.

Three patterns to choose from (all documented in `docs/API.md`
"TheoProvider integration recipes"):

1. **`FilePollTheoProvider`** — write theos to a CSV/JSON, bot
   polls. Easiest. Works with any tooling that can write a file.
2. **`HttpPollTheoProvider`** — host a JSON endpoint. Works with
   any model behind a service.
3. **Custom class** — implement `TheoProvider` protocol. For
   stateful providers (live data feeds, anchored math, etc.).

The `StubTheoProvider` already shipped in `deploy/_stub_theo.py`
returns `confidence=0` for every strike, so the bot is safe by
default (quotes nothing until the operator either sets manual
theo overrides via the dashboard OR registers a real provider).

---

## 90-second recipient runbook

For the recipient's README:

```bash
# 1. Install
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 2. Kalshi credentials (one-time)
export KALSHI_API_KEY="..."
export KALSHI_PRIVATE_KEY_PATH="/path/to/key.pem"

# 3. Dashboard secret (one-time per deployment)
export LIPMM_CONTROL_SECRET="$(python -c 'import secrets; print(secrets.token_hex(16))')"
echo "$LIPMM_CONTROL_SECRET"   # save this — paste on dashboard login

# 4. Run with safe-default stub theo
python -m deploy.lipmm_run --event-ticker KXSAMPLEEVENT-XXX

# 5. Open dashboard
open http://localhost:5050
# Paste the secret. Set per-strike theo overrides via the
# expanded-strike form. Bot starts quoting once overrides are set.
```

---

## Verification of a clean build

After copying + genericizing, the recipient should:

```bash
pytest tests/ --ignore=tests/test_benchmarks.py --ignore=tests/test_kalshi_client.py
```

Should show **~1500+ passing tests** with no errors. If any test
fails with `ImportError: cannot import name 'TruEV...'`, you missed
an edit in `tests/` or `lipmm/theo/providers/__init__.py`.

Then:

```bash
ruff check .
```

Should pass clean (the framework's own lint config is in
`pyproject.toml`).

Finally:

```bash
python -m deploy.lipmm_run --event-ticker KXSAMPLEEVENT-XXX --help
```

Should print the CLI usage with NO `--truev-*` flags listed.

---

## Quick directory copy script

For convenience, a one-liner that copies the right tree
(BSD/macOS `rsync` flavor; adjust for Linux):

```bash
# From the SOURCE repo root, copying to ~/dist
rsync -av \
  --include='/lipmm/***' \
  --include='/feeds/__init__.py' \
  --include='/feeds/kalshi/' \
  --include='/feeds/kalshi/__init__.py' \
  --include='/feeds/kalshi/__main__.py' \
  --include='/feeds/kalshi/auth.py' \
  --include='/feeds/kalshi/capture.py' \
  --include='/feeds/kalshi/client.py' \
  --include='/feeds/kalshi/errors.py' \
  --include='/feeds/kalshi/events.py' \
  --include='/deploy/__init__.py' \
  --include='/deploy/_stub_theo.py' \
  --include='/deploy/lipmm_run.py' \
  --include='/deploy/README_quickstart.md' \
  --include='/docs/***' \
  --include='/tests/' \
  --include='/tests/__init__.py' \
  --include='/tests/_bs_reference.py' \
  --include='/tests/conftest.py' \
  --include='/tests/test_*.py' \
  --include='/pyproject.toml' \
  --include='/README.md' \
  --include='/.gitignore' \
  --exclude='*__pycache__*' \
  --exclude='*.pyc' \
  --exclude='*.egg-info' \
  --exclude='/lipmm/theo/providers/truev.py' \
  --exclude='/lipmm/theo/providers/_truev_index.py' \
  --exclude='/feeds/kalshi/lip_pool.py' \
  --exclude='/feeds/kalshi/lip_score.py' \
  --exclude='/deploy/truev_*' \
  --exclude='/tests/test_truev_*' \
  --exclude='/tests/test_lip_pool.py' \
  --exclude='/tests/test_lip_score.py' \
  --exclude='/tests/test_lip_mode_sticky_integration.py' \
  --exclude='/tests/test_ibkr_*' \
  --exclude='/tests/test_cme_*' \
  --exclude='/tests/test_cbot_*' \
  --exclude='/tests/test_goldman_roll.py' \
  --exclude='/tests/test_implied_vol.py' \
  --exclude='/tests/test_corridor.py' \
  --exclude='/tests/test_markout.py' \
  --exclude='*' \
  ./ ~/dist/
```

Then perform the genericization edits listed above.

---

## Recommended commit at the end

If you're pushing the distribution to a fresh repo:

```bash
cd ~/dist
git init
git add .
git commit -m "Initial commit: generic lipmm market-making framework

A Kalshi-binary market-maker bot framework. Plug-in TheoProvider
architecture; safe-by-default StubTheoProvider; operator dashboard
with JWT auth, runtime knobs, manual orders, and decision feed.
Strip the genericization comments before sharing further."
```
