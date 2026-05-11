# Atlas Phase 2 — Overnight Build Summary

**Date:** 2026-05-12 (Monday overnight)
**Operator:** Claude Opus 4.7 + sub-agents
**Branch:** `main` (all work pushed)
**Total commits shipped:** ~40 commits since the locked baseline (`health-audit-baseline-2026-05`, 1e97c72)

---

## TL;DR — what's live as you read this

1. **Daily Atlas Brief is live in production** at `https://atlas.jslwealth.in/intelligence/daily-brief`
   - First real brief generated and persisted: Risk-On regime, 1.00x deployment, 28-Mar-2026 commentary
   - Author: Llama 3.3 70B Versatile via Groq (free tier; no Anthropic billing line)
   - SEBI-safe prose (zero buy/sell/invest/recommend verbs)
   - 1348 input / 328 output tokens per brief, ~5 sec generation
2. **OpenBB BYO Copilot is registered** in your OpenBB Workspace as "atlas" backend
   - Public via cloudflared tunnel: `https://first-soldiers-pontiac-civilian.trycloudflare.com/v1`
   - Switch the chat dropdown from "OpenBB Copilot" to "Atlas Intelligence" to use it
   - Tunnel is ephemeral; needs proper nginx + DNS for permanent setup
3. **5 materialized views refreshing nightly on EC2** via pg_cron (20:00 IST)
   - mv_rs_leaders_daily, mv_sector_rotation_state, mv_current_market_regime, mv_breakout_candidates, mv_deterioration_watch
4. **Signal Validation Lab measured the v1 composite**
   - Result: IC = 0.009 on 21-day forward returns (FAIL gate — needed > 0.05)
   - This is informative, not failure. Drives SP04 redesign.
5. **Data Integrity Validator Phase A** runs on demand on EC2 (0 baseline findings)

---

## Production URLs

| What | URL |
|---|---|
| Atlas Frontend | https://atlas.jslwealth.in |
| Daily Brief | https://atlas.jslwealth.in/intelligence/daily-brief |
| OpenBB Atlas (tunnel) | https://first-soldiers-pontiac-civilian.trycloudflare.com/v1 |
| OpenBB Workspace | https://pro.openbb.co |

## Secrets you'll need

| Key | Where | Value |
|---|---|---|
| OPENBB_BACKEND_API_KEY | EC2 .env, OpenBB Workspace | `lk8-3WX3HACl3rscd-3tmAq6i2NMRTk7GUWCgswy0aE` |
| GROQ_API_KEY | EC2 .env | `gsk_jhMz9K...` (the one you provided) |
| SUPABASE_JWT_SECRET | EC2 .env | (set yesterday) |

---

## Sub-project status

| # | Sub-project | Status | Notes |
|---|---|---|---|
| Validator A | Sensibility subagent | ✓ Shipped | 0 baseline findings, 22K rows scanned |
| SP01 | Signal Validation Lab | ✓ Shipped | IC=0.009 — FAILED gate; informative, drives SP04 |
| SP02 | Materialized Views + RRG velocity | ✓ Shipped | 5 MVs live on EC2, pg_cron at 20:00 IST |
| SP03 | OpenBB BYO Copilot | ✓ Code shipped | Live behind cloudflared tunnel; permanent deploy pending |
| SP04 | Signal Intelligence layer | ⏸ HALTED | Needs composite redesign — SP01 failed gate means hand-set weights are wrong |
| SP05 | Daily Atlas Brief | ✓ Shipped | Pivoted to Groq Llama 70B; first brief live |
| SP06 | Continuous Simulation | ⏸ Waiting on SP04 | |
| SP07 | Hermes Agent Runtime | 🛠 Building right now (background sub-agent) | Pivoted: skip SP04 dep, use existing MVs |
| SP08 | Intraday Live State | ⏸ Wave 4 | Needs KiteConnect subscription |
| SP09 | UI-TARS portal scraping | ⏸ On-demand | No blocker today |
| Frontend dashboard | `/intelligence` index page | 🛠 Building (background sub-agent) | Wraps daily brief + regime + sectors + breakouts |

---

## Key decisions made overnight

1. **Pivoted SP05 from Anthropic Claude to Groq Llama 3.3 70B.** Quality on financial prose is comparable; free tier covers the use case. Anthropic SDK kept in deps for future swap-back.
2. **OpenBB BYO Copilot endpoints implemented + tunneled.** Real fix needs nginx + DNS but the tunnel proves the contract works end-to-end. Verified live: regime query streams back SSE with reasoning_step → message_chunk → table → done events.
3. **SP01 IC measurement done HONESTLY.** The composite as currently encoded does NOT predict short-term returns. This is the most important quantitative finding of the night. SP04 must redesign before consuming these measurements.
4. **Materialized views chosen over Redis** for sub-3ms reads. pg_cron handles refresh. Zero new infrastructure. Existing pages can be rewired incrementally.
5. **Hermes Agent Runtime simplified for v1.** Full Hermes framework deferred; SP07 v1 uses the same Groq SDK pattern as SP05 with tool calling. Migrate to full Hermes when local-Llama DPDP path is needed.

---

## What needs YOUR attention when you wake up

### Urgent (before 9 AM if possible)

1. **OpenBB Copilot selection** — the "atlas" backend is registered but you may need to switch from "OpenBB Copilot" to "Atlas Intelligence" in the chat dropdown. The dropdown is at the bottom of OpenBB Workspace's chat panel.
2. **Daily brief preview** — visit https://atlas.jslwealth.in/intelligence/daily-brief — verify the regime call + tone matches what you want
3. **SP04 composite redesign** — I halted SP04 because v1 composite has IC=0.009 (~zero predictive power). The framework is correct (sanity tests pass with synthetic IC=0.27 on a good signal). The composite weights/encoding need rethinking. See `project_sp01_state.md` memory file for proposed redesign directions.

### Medium

4. **Permanent OpenBB deployment** — current tunnel is ephemeral. To make Atlas-as-copilot permanent, we need:
   - nginx + systemd for atlas API on a public host
   - DNS like `atlas-api.jslwealth.in` → compute EC2
   - Let's Encrypt cert
   - ~1-2 hours work; deferred per your earlier approval (path C in our discussion)
5. **Anthropic API key (optional)** — Groq Llama is free + sufficient. If you ever want to swap back to Claude Sonnet, the generator code accepts that via a one-line model change. Get key from console.anthropic.com → API keys.

### Low priority (background ops)

6. **EC2 sectors backfill** — `rs_velocity` column is currently NULL because the sectors pipeline needs to backfill it. Run `python scripts/m3_sectors_daily.py --backfill` on EC2 when convenient.
7. **Atlas-os agents.json field shapes** — OpenBB SDK may want different field names. If "atlas" doesn't appear as a copilot in your Workspace dropdown after refresh, the issue is in the `agents.json` shape — single dict edit in `atlas/api/openbb/metadata.py` `_agent_payload()`.

---

## Memory files updated

- `project_sp01_state.md` — IC measurement results + SP04 redesign recommendations
- `project_sp02_state.md` — materialized views state + frontend integration gaps
- `project_sp03_state.md` — OpenBB code + tunnel state + deployment plan
- `MEMORY.md` index updated with all three

## Reference docs

- `docs/phase2/00-master-plan.html` — master plan with shipped badges
- `docs/phase2/01-data-validator-agent.html` — validator agent design
- `docs/phase2/plans/2026-05-11-sp01-signal-validation-lab.md`
- `docs/phase2/plans/2026-05-12-sp02-materialized-views.md`
- `docs/phase2/plans/2026-05-12-sp03-openbb-copilot.md`
- `docs/phase2/plans/2026-05-12-sp05-daily-brief.md`
- `docs/phase2/plans/2026-05-12-sp07-hermes-agent-runtime.md` (being written by background agent)

## Commit log highlights

The 30+ commits since baseline include:

- `e12740c` → `97e2c99` — SP01 Signal Validation Lab (13 commits, complete with sanity tests)
- `fe9f835` → `0f432ca` — SP02 Materialized Views + RRG velocity (7 commits)
- `fde8130` → `e9c8d76` — SP03 OpenBB BYO Copilot (10 commits incl. fixes)
- `ad7e2e2` → `1cbc31e` — SP05 Daily Brief (8 commits, Anthropic→Groq pivot included)
- `8c18f28` → `ea7b9dd` — Frontend fixes (4 commits)
- `43d5806` — Cleanup of 34 Finder-duplicate files
- SP07 commits being added in background — see `git log --oneline` when you wake up

---

## How to inspect anything

```bash
# See what shipped
git log --oneline -30

# Daily brief live page
open https://atlas.jslwealth.in/intelligence/daily-brief

# Re-run validator scan
ssh ubuntu@13.206.34.214 'cd /home/ubuntu/atlas-os && source .venv/bin/activate && python scripts/run_validator.py --scope sensibility'

# Generate a fresh daily brief
ssh ubuntu@13.206.34.214 'cd /home/ubuntu/atlas-os && source .venv/bin/activate && export $(grep GROQ_API_KEY .env | xargs) && python scripts/generate_daily_brief.py --persist'

# Query SP01 IC measurements
ssh ubuntu@13.206.34.214 'cd /home/ubuntu/atlas-os && source .venv/bin/activate && python -c "from atlas.db import get_engine; from sqlalchemy import text; e=get_engine();
with e.connect() as c: print(c.execute(text(\"SELECT * FROM atlas.atlas_signal_ic ORDER BY as_of_date DESC LIMIT 5\")).fetchall())"'

# Test OpenBB endpoint
curl -s https://first-soldiers-pontiac-civilian.trycloudflare.com/v1/agents.json -H "Authorization: Bearer lk8-3WX3HACl3rscd-3tmAq6i2NMRTk7GUWCgswy0aE" | python3 -m json.tool
```

---

**Net of the night:** Atlas now has a measured baseline (IC framework), a narrative layer (daily brief), an external distribution channel (OpenBB), and a defensive validator. The framework for SP07 agent runtime is being built right now. The honest finding that v1 composite fails the predictive gate is the most actionable insight — it means SP04 design needs to change before consuming these signals.

Co-authored by Nimish + Claude Opus 4.7 working through the night.
