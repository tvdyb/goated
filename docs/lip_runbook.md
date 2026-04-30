# LIP Bot Runbook

3am-friendly. What to look for, where to look, what to do.

## Is the bot in COOLDOWN?

```bash
screen -r bot
# Look for these patterns in recent log lines:
# STICKY TRANSITION <ticker> <side>: AGGRESSIVE -> COOLDOWN
# STICKY <ticker> <side>: COOLDOWN cancel of <id>
```

Or via decision logs:

```bash
python tools/grep_decisions.py --state COOLDOWN --tail 20 --compact
python tools/grep_decisions.py --transition "AGGRESSIVE -> COOLDOWN"
```

A side enters COOLDOWN when AGGRESSIVE persists past `max_aggressive_duration_seconds` (default 300s). It auto-recovers after `cooldown_seconds` (default 600s).

## Manually pulling all orders if circuit breakers misfire

**Option A — restart the bot (safest):**

```bash
screen -r bot
# Ctrl+C to interrupt → triggers shutdown which calls _cancel_all
# Re-run: python -m deploy.lip_mode --config deploy/config_lip.yaml
# Detach: Ctrl+A then D
```

**Option B — Kalshi web UI:**

Log in at https://kalshi.com → Portfolio → Orders → cancel any leftover orders. Use this if the bot is stuck or unreachable.

**Option C — manual API script (last resort):** see `tools/cancel_all.py` if it exists, else fall back to Option B.

## Where to find the current decision log

```bash
# Today's file (UTC date boundary)
ls -la logs/decisions/decisions_$(date -u +%Y-%m-%d).jsonl

# Tail it live
tail -f logs/decisions/decisions_$(date -u +%Y-%m-%d).jsonl | jq .
```

If decisions are sub-rotated (>500MB in one day), files are suffixed: `.01.jsonl`, `.02.jsonl`, etc.

## Inspection commands

```bash
# Compact view of last 50 cycles
python tools/grep_decisions.py --tail 50 --compact

# Every COOLDOWN entry today
python tools/grep_decisions.py --transition "AGGRESSIVE -> COOLDOWN"

# Every cycle on a specific strike between 13:00 and 14:00 UTC
python tools/grep_decisions.py --ticker T1186.99 --since 13:00 --until 14:00

# Every early-return cycle (potential bug indicator)
python tools/grep_decisions.py --early-return --tail 20

# Stream live — most useful first command after restart
tail -f logs/decisions/decisions_$(date -u +%Y-%m-%d).jsonl | jq .
```

## Tunable parameters in `deploy/config_lip.yaml`

| Param | Default | What it does |
|---|---|---|
| `lip.contracts_per_side` | 12 | base order size per side per strike |
| `lip.size_jitter` | 3 | ± randomization to reduce bot fingerprint |
| `lip.max_distance_from_best` | 1 | how far from top-of-book in active mode |
| `lip.theo_tolerance` | 2 | anti-spoofing window around theo |
| `lip.sticky.enabled` | true | master switch for sticky state machine |
| `lip.sticky.desert_jump_cents` | 5 | how aggressively to penny in AGGRESSIVE |
| `lip.sticky.min_distance_from_theo` | 15 | floor on how close to theo we'll quote |
| `lip.sticky.snapshots_at_1x_required` | 10 | cycles at 1.0x mult needed before relax |
| `lip.sticky.relax_total_steps` | 10 | how many cycles to walk back to natural |
| `lip.sticky.theo_stability_cents` | 2.0 | max theo drift during AGGRESSIVE lock |
| `lip.sticky.max_aggressive_duration_seconds` | 300 | circuit breaker timeout (5 min) |
| `lip.sticky.cooldown_seconds` | 600 | idle duration after circuit breaker (10 min) |
| `loop.cycle_seconds` | 3 | bot loop interval |
| `synthetic.forward_override` | 0 | manual forward (0 = use TE/yfinance auto) |

When tuning: change one knob at a time, observe behavior in decision logs for 1-2 hours, decide.

## Disk hygiene

Decision logs accrue ~290MB/day for soy-only. Recommended cron entry on Mac Mini:

```cron
0 4 * * *  find /path/to/goated/logs/decisions -name "decisions_*.jsonl" -mtime +30 -delete
```

Adjust `+30` (days to keep) to taste.
