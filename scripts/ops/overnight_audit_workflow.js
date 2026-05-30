export const meta = {
  name: 'atlas-overnight-audit',
  description: 'Exhaustive read-only audit of Atlas OS: data pipeline, backend arch, frontend coherence, API quality, secrets, code health. Synthesizes one ranked report + fix plan.',
  phases: [
    { title: 'Audit', detail: '6 parallel auditors across data/backend/frontend/api/security/health' },
    { title: 'Verify', detail: 'adversarially verify CRITICAL/HIGH findings' },
    { title: 'Synthesize', detail: 'rank by blast-radius × visibility × complexity, write report' },
  ],
}

// ---------------------------------------------------------------------------
// Shared context fed to every auditor — facts already gathered by the main
// session so agents start from truth, not rediscovery.
// ---------------------------------------------------------------------------
const REPO = '/Users/nimishshah/Documents/GitHub/atlas-os'

const DB_RECIPE = `
DB ACCESS (production Supabase via EC2 — local Mac psycopg2 is broken, ALWAYS go through the 'atlas' SSH host):
  ssh atlas 'cd /home/ubuntu/atlas-os && source .venv/bin/activate && python3 -c "
import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
load_dotenv(\\".env\\")
e = create_engine(os.environ[\\"ATLAS_DB_URL\\"])
with e.connect() as c:   # IMPORTANT: open a FRESH connection per query — one failed query aborts the whole tx (InFailedSqlTransaction)
    rows = c.execute(text(\\"SELECT ...\\")).fetchall()
    for r in rows: print(r)
"'
The schema is 'atlas'. There is a stray public.alembic_version (=112) and the REAL one is atlas.atlas_alembic_version (=120). Use atlas.* always.`

const FACTS = `
ALREADY-PROVEN FACTS (do not re-derive, build on these):
- Production alembic head = 120 (atlas.atlas_alembic_version). Migrations all applied 2026-05-29.
- Today is 2026-05-29 (Fri) close. "Stale" = latest data older than 2026-05-29.
- SOURCE TABLES FRESH (writers ran today): atlas_sector_metrics_daily (05-29), atlas_market_regime_daily (05-29), atlas_stock_conviction_daily (05-29), tv_metrics (05-29, 400/750 rows).
- MATERIALIZED VIEWS STALE (the frontend reads these):
    mv_market_regime_landing  latest=2026-05-22 (7d stale)  -> landing page
    mv_stock_list_v6          latest=2026-05-22 (7d stale)  -> stocks list
    mv_markets_rs_grid        latest=2026-05-26 (3d stale)  -> markets-rs
    mv_stock_landscape        latest=2026-05-27 (2d stale)  -> stock bubble/matrix
    mv_sector_deepdive / mv_etf_list_v6 / mv_etf_deepdive / mv_fund_list_v6 / mv_fund_deepdive / mv_calls_performance: no as_of_date column, freshness unknown
- STALE BASE WRITERS: atlas_fund_scorecard (05-22, 7d), atlas_signal_calls (05-27, 2d -> "d3 for every stock" symptom), atlas_etf_scorecard (05-27).
- pg_cron job 'mv_refresh_v6_all' runs 21:45 daily but MVs are not advancing to source-data freshness -> PRIMARY SUSPECT.
- Other cron: atlas_mv_regime/rotation/breakouts/deterioration/rs_leaders (23:30), atlas_mv_conviction (14:45), tv_screener_nightly (15:30 weekdays), atlas_macro_nightly (14:45).`

const MEMORY = `
HONOR THESE PROJECT MEMORIES:
- [[everything-clickable]]: every ticker/sector/fund/cell name must be a Link to its deep-dive; dead text identifiers are an anti-pattern.
- [[atlas-explainer-flywheel]]: never a black box; every metric/auto-action surfaces the math + plain-English.
- CONTEXT.md is canonical for vocabulary. Regime states (live): Risk-On / Constructive / Cautious / Risk-Off. Verdict labels: BUY/ACCUMULATE/WATCH/HOLD/AVOID/SELL/WAIT. Cell states: POSITIVE/NEUTRAL/NEGATIVE.
- Modulith rule: atlas/<context> packages may only cross-import via atlas.primitives, atlas.db, atlas.config, or a context's public __init__.
- Tiered LOC limits: 600 src / 800 test / 250 page-shell. Escape valve: '# allow-large: <reason>'.
- Decimal for money. Tz-aware datetimes. No float for money.`

const FINDINGS_SCHEMA = {
  type: 'object',
  required: ['summary', 'findings'],
  properties: {
    summary: { type: 'string', description: 'One-paragraph executive summary of this dimension.' },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        required: ['id', 'severity', 'title', 'location', 'evidence', 'impact', 'fix', 'fix_complexity'],
        properties: {
          id: { type: 'string', description: 'short slug, e.g. mv-refresh-broken' },
          severity: { type: 'string', enum: ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'] },
          title: { type: 'string' },
          location: { type: 'string', description: 'file:line, table name, cron job, or route' },
          evidence: { type: 'string', description: 'concrete proof — code snippet, query result, row count' },
          impact: { type: 'string', description: 'user-visible + system effect' },
          fix: { type: 'string', description: 'specific remediation, not vague' },
          fix_complexity: { type: 'string', enum: ['S', 'M', 'L'], description: 'S<1h, M few hours, L day+' },
          user_visible: { type: 'boolean' },
        },
      },
    },
  },
}

const VERDICT_SCHEMA = {
  type: 'object',
  required: ['id', 'verdict', 'reason'],
  properties: {
    id: { type: 'string' },
    verdict: { type: 'string', enum: ['CONFIRMED', 'REFUTED', 'UNCERTAIN'] },
    reason: { type: 'string' },
    corrected_severity: { type: 'string', enum: ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'NONE'] },
  },
}

const COMMON = `${DB_RECIPE}\n${FACTS}\n${MEMORY}\n\nRepo root: ${REPO}. You are auditing READ-ONLY. Do NOT edit/write/commit any file. Use Read, Grep, Bash (read-only: git log, grep, wc, ssh atlas for DB reads), and ToolSearch for MCP if needed. Return ONLY validated findings via the StructuredOutput tool. Be concrete: every finding needs a file:line or a query result as evidence. No speculation without evidence.`

// ---------------------------------------------------------------------------
// Phase A — 6 parallel auditors
// ---------------------------------------------------------------------------
const AUDITORS = [
  {
    key: 'data-pipeline',
    prompt: `${COMMON}

DIMENSION: DATA PIPELINE + CRON HEALTH + MV STALENESS. This is the highest-priority audit.

Your job: root-cause WHY the v6 materialized views are stale (05-22/05-26/05-27) while their source tables are fresh (05-29), and inventory every data-completeness gap.

Investigate:
1. Read migrations/versions/*pg_cron*.py and the mv_refresh_v6_all job. What does it actually refresh? ssh atlas and query cron.job + cron.job_run_details for jobname like '%refresh%' / '%v6%' — did it run at 21:45 on 05-29? Did it succeed? What was return_message? If it "succeeded" but MVs didn't advance, the MV definitions themselves must be anchored to a stale date OR the refresh list is incomplete (missing mv_market_regime_landing, mv_stock_list_v6 from the refresh set).
2. For EACH stale MV, read its CREATE MATERIALIZED VIEW definition (in migrations/) and find the date anchor. Is it 'WHERE date = (SELECT MAX...)' (self-correcting) or a hardcoded/CURRENT_DATE-based filter that breaks on weekends/holidays?
3. Inventory ALL v6 MVs: name, row count, latest as_of_date (use the actual date column — some are as_of_date, some snapshot_date, some have none). Build the complete staleness table.
4. Check the 3 stale base writers: why is atlas_fund_scorecard 7 days stale? atlas_signal_calls 2 days (this causes "d3 for every stock")? atlas_etf_scorecard 2 days? Find the writer + its cron + last run.
5. Sector data specifically: the user reports "empty data at sector level". Query atlas_sector_metrics_daily for 05-29 — how many sectors have NULL rs_1m / pct_above_ema20 / hhi? Check mv_sector_deepdive + mv_sector_cards for empty/null rows.
6. Identify the EXACT safe command sequence to bring everything to 05-29 Friday close (which writers to run, in what order, then which MV refresh). Reference scripts/ops/run_atlas_nightly.sh if it exists.

Deliver findings with the mv_refresh root cause as the top CRITICAL finding, plus the remediation command sequence as a fix.`,
  },
  {
    key: 'backend-arch',
    prompt: `${COMMON}

DIMENSION: BACKEND ARCHITECTURE + CODE QUALITY.

Investigate:
1. Large files near/over the 600-LOC limit (known: atlas/discovery/deep_search_candidates.py=2027, engine.py=1339, compute/sectors.py=1274, features/scorecard_writer.py=1231, inference/etf_scorecard.py=1074, fund_scorecard.py=1068, preflight.py=923). For each >800 LOC: is there an '# allow-large' justification? Is it a genuine god-file that's a failure point (mixed responsibilities, hard to test)? Recommend split boundaries.
2. Modulith violations: grep for cross-context imports that bypass atlas.primitives/db/config/__init__. e.g. 'from atlas.compute' inside atlas/inference, etc. List every violation.
3. Dead/stale code: modules with zero importers, functions defined but never called, commented-out blocks, TODO/FIXME/HACK markers older than the v6 rebuild. Use grep + git log to date them.
4. Inefficient patterns (per data-engineering rules): df.iterrows(), df.apply(lambda) on large frames, pd.read_sql('SELECT * ...') without WHERE, fetchall() on large results, N+1 query loops. grep across atlas/.
5. Inconsistent error handling: bare 'except:' clauses, swallowed exceptions, missing structured logging.
6. Duplicate logic: e.g. is there both markets-rs.ts and markets_rs.ts equivalents in backend? Two scorecard paths?

Rank god-files that are production failure points as HIGH.`,
  },
  {
    key: 'frontend-coherence',
    prompt: `${COMMON}

DIMENSION: FRONTEND DATA COHERENCE + INCONSISTENCY. The user's biggest complaint.

Specific reported bugs to root-cause:
A) On the landing page (/), the big "Cautious" regime verdict at top, but the Trend/Breadth/Momentum scorecard tiles show GREEN, and one says trend is "mixed" — contradictory signals in one view. Trace EXACTLY which data source each element reads:
   - The big verdict (RegimeVerdict): reads getCurrentRegime() -> atlas_market_regime_daily.regime_state
   - The scorecard tiles (SignalScorecard): reads getRegimeScorecard() + the regime row. Read frontend/src/components/regime/SignalScorecard.tsx buildTrendTile/buildBreadthTile/buildMomentumTile — what thresholds decide green vs red? Do they DISAGREE with the regime classifier's own thresholds (atlas/compute/regime.py)? A tile can be green (breadth 66% > 50%) while the regime is Cautious because the classifier weighs VIX/McClellan too. Is this a genuine logic inconsistency or just missing explanation? Determine which.
   - Decide: is the fix (a) reconcile thresholds, (b) add explanation linking tiles to verdict, or (c) a real bug.
B) Empty cards / empty spaces: grep components for places that render nothing when data is null (no empty-state). List routes with likely-empty sections given the stale-MV facts above.
C) Unexplained terms / incoherent text: scan v6 components for jargon shown to users without a tooltip/gloss (e.g. raw column names, "McClellan", "HHI", "dispersion", cell codes) — violates [[atlas-explainer-flywheel]].
D) [[everything-clickable]] violations: tickers/sectors/funds rendered as plain text not Links.
E) Stale-data-driven inconsistency: which pages will show contradictory things specifically BECAUSE they mix a fresh source table with a stale MV?

Map each route (40 page.tsx files) to its query modules. Flag every coherence risk with the exact file:line.`,
  },
  {
    key: 'api-quality',
    prompt: `${COMMON}

DIMENSION: API QUALITY + HEALTH.

Investigate atlas/api/*.py and atlas/tv/routes.py + the FastAPI app:
1. Endpoint inventory: list every route, method, path. Flag any non-versioned or non-terse-URL routes (CONTEXT.md requires Bloomberg-style /v1/screen.stocks).
2. Response envelope compliance: CONTEXT.md mandates {"data":..., "meta":{data_as_of, fetched_at, source}} and error {"error_code", "field", "message", "context"}. grep for endpoints returning raw dicts/lists without the envelope.
3. Missing: cursor pagination (not offset), X-RateLimit-* headers, Idempotency-Key on writes, Pydantic v2 request/response models (not bare dicts).
4. Auth: which endpoints lack the Supabase JWT middleware / request.state.user check? Any unauthenticated write endpoints?
5. The new TV routes (rs-ratios, peer-matrix, tv/metrics): the summary says they're "not publicly exposed (needs nginx + systemd)". Confirm whether they're registered in the FastAPI app at all and whether they follow the envelope.
6. Error handling: generic 500s vs specific HTTPException with status codes.

Rank unauthenticated writes or missing-envelope public endpoints as HIGH.`,
  },
  {
    key: 'secrets-security',
    prompt: `${COMMON}

DIMENSION: SECRETS + SECURITY.

Investigate:
1. Hardcoded credentials: grep the repo (atlas/, frontend/src/, scripts/, migrations/) for password=, api_key=, secret=, token=, bearer, postgres://...@, AWS keys, Groq/OpenAI/Anthropic keys committed in source. NOTE: the .env on EC2 has real creds — check if any .env or secret leaked into git history (git log -p -S 'password'). The known prod DB password is in .env (correct) — flag if it appears in ANY committed file.
2. PII in log lines: grep for log statements that interpolate user emails, names, PAN, portfolio holdings (financial-domain rule: no PII in logs).
3. SQL injection: f-string / %-format SQL with user input (vs parameterized text(:param)). grep atlas/ for f"SELECT ... {var}" and .format( in SQL contexts.
4. Frontend secret exposure: NEXT_PUBLIC_ vars that shouldn't be public; API keys in client components; the atlas_auth cookie mechanism — is ATLAS_PASSWORD hardcoded anywhere in frontend source?
5. Auth bypass: routes/pages that skip the auth check.
6. Dependency CVEs: check pyproject.toml + frontend/package.json for obviously outdated security-sensitive deps.

Treat any committed credential or SQL injection vector as CRITICAL.`,
  },
  {
    key: 'code-health',
    prompt: `${COMMON}

DIMENSION: CODE HEALTH — unused code, type errors, test gaps, stale artifacts.

Investigate:
1. TypeScript errors: run 'cd ${REPO}/frontend && npx tsc --noEmit 2>&1 | grep "error TS"'. Categorize: stale .next cache errors vs real source errors vs test-fixture errors. The main session saw ~36 — confirm none are in shipped source (app/, components/, lib/), only tests/.next.
2. Unused imports/exports: frontend — grep for exported functions/types with zero importers. Backend — unused imports (ruff would catch; run 'cd ${REPO} && ruff check atlas/ --select F401,F811 2>&1 | head -40').
3. Duplicate files: the known markets-rs.ts vs markets_rs.ts collision (both export getMarketsRsPage, different return types, page imports the underscore one — the kebab one is orphaned). Find ALL such duplicate-convention pairs. Also orphaned ETFTraderViewHeader.tsx (dropped in ETF redesign).
4. Dead routes: page.tsx files for routes no longer linked from nav. Cross-ref against the nav/sidebar component.
5. Test coverage gaps: backend modules in atlas/ (especially the v6 contexts: features, decisions, regime, verdict, tv) with no corresponding tests/. Frontend query modules without .test.ts.
6. Stale docs/specs: docs/ files referencing retired approaches (v6 RS Trading Model retired, SDE set aside) that could mislead.
7. Build artifacts / backup dirs committed by accident.

For each unused/orphaned item give the exact path + proof of zero references.`,
  },
]

phase('Audit')
log('Atlas overnight audit: 6 parallel auditors fanning out (read-only)...')

const rawResults = await parallel(
  AUDITORS.map(a => () =>
    agent(a.prompt, {
      label: `audit:${a.key}`,
      phase: 'Audit',
      schema: FINDINGS_SCHEMA,
      agentType: 'Explore',
    }).then(r => ({ key: a.key, ...r })).catch(() => null)
  )
)

const audits = rawResults.filter(Boolean)
const allFindings = audits.flatMap(a =>
  (a.findings || []).map(f => ({ ...f, dimension: a.key }))
)
log(`Audit complete: ${allFindings.length} findings across ${audits.length} dimensions.`)

// ---------------------------------------------------------------------------
// Phase B — adversarially verify CRITICAL + HIGH findings
// ---------------------------------------------------------------------------
phase('Verify')
const toVerify = allFindings.filter(f => f.severity === 'CRITICAL' || f.severity === 'HIGH')
log(`Verifying ${toVerify.length} CRITICAL/HIGH findings adversarially...`)

const verdicts = await parallel(
  toVerify.map(f => () =>
    agent(
      `${DB_RECIPE}\n\nYou are an adversarial verifier. A prior auditor reported this finding. Try to REFUTE it. Read the actual code/query the evidence cites and confirm whether it is real, mis-stated, or a false positive. Default to UNCERTAIN if you cannot independently confirm.

FINDING id=${f.id} severity=${f.severity}
  dimension: ${f.dimension}
  title: ${f.title}
  location: ${f.location}
  evidence: ${f.evidence}
  impact: ${f.impact}

Repo: ${REPO}. Read-only. Return your verdict. If CONFIRMED, optionally adjust severity. If the evidence doesn't hold up, REFUTE with the corrected reality.`,
      { label: `verify:${f.id}`, phase: 'Verify', schema: VERDICT_SCHEMA, agentType: 'Explore' }
    ).then(v => ({ ...f, verification: v })).catch(() => ({ ...f, verification: { verdict: 'UNCERTAIN', reason: 'verifier errored' } }))
  )
)

const confirmed = verdicts.filter(v => v.verification?.verdict !== 'REFUTED')
const refuted = verdicts.filter(v => v.verification?.verdict === 'REFUTED')
log(`Verified: ${confirmed.length} hold up, ${refuted.length} refuted/dropped.`)

// Merge verified-high with the untouched medium/low
const mediumLow = allFindings.filter(f => f.severity === 'MEDIUM' || f.severity === 'LOW')
const finalFindings = [...confirmed, ...mediumLow]

// ---------------------------------------------------------------------------
// Phase C — synthesize ranked report + fix plan, write to disk
// ---------------------------------------------------------------------------
phase('Synthesize')
log('Synthesizing ranked report + chunked fix plan...')

const report = await agent(
  `You are the lead engineer writing the definitive overnight audit report for Atlas OS, a production fintech equity-intelligence platform heading toward commercial scale.

You are given ${finalFindings.length} verified findings (CRITICAL/HIGH were adversarially verified; ${refuted.length} were refuted and excluded). Plus ${audits.length} dimension summaries.

DIMENSION SUMMARIES:
${audits.map(a => `### ${a.key}\n${a.summary}`).join('\n\n')}

VERIFIED FINDINGS (JSON):
${JSON.stringify(finalFindings, null, 1)}

REFUTED (for transparency, list briefly so the reader knows what was checked-and-cleared):
${JSON.stringify(refuted.map(r => ({ id: r.id, title: r.title, why: r.verification?.reason })), null, 1)}

Write a comprehensive markdown report and SAVE it with the Write tool to:
  ${REPO}/docs/v6/2026-05-30-overnight-audit.md

Report structure:
1. Executive summary — the 3-5 things that matter most, bad news at the top. Lead with the MV-refresh staleness root cause.
2. "Fix tonight (safe, operational)" — the exact command sequence to bring all data to 2026-05-29 Friday close WITHOUT code changes (re-run writers + MV refresh). This is the highest-value, lowest-risk action.
3. Ranked findings table — sort by priority score = (blast_radius × user_visibility × inverse_complexity). Columns: Priority, Severity, ID, Title, Location, Fix, Complexity, Dimension.
4. Per-dimension detail sections — full evidence + fix for each finding, grouped by dimension.
5. Chunked fix plan — group findings into discrete, independently-shippable chunks (each = one session with review). Order by dependency + impact. Each chunk: name, findings included, files touched, verification step, est complexity. Explicitly mark which chunks are safe to automate vs need human review.
6. "Do NOT touch" list — things that look broken but are intentional (cite the refuted findings + any CONTEXT.md-justified design).
7. Open questions for the user.

Be specific and honest. This report drives tomorrow's work. Cite file:line and query results. After writing the file, return a 10-line summary of what you wrote + the count of CRITICAL/HIGH/MEDIUM/LOW findings.`,
  { label: 'synthesize:report', phase: 'Synthesize' }
)

return {
  dimensions: audits.length,
  totalFindings: allFindings.length,
  verifiedHigh: confirmed.length,
  refuted: refuted.length,
  finalCount: finalFindings.length,
  reportSummary: report,
  severityCounts: {
    critical: finalFindings.filter(f => f.severity === 'CRITICAL').length,
    high: finalFindings.filter(f => f.severity === 'HIGH').length,
    medium: finalFindings.filter(f => f.severity === 'MEDIUM').length,
    low: finalFindings.filter(f => f.severity === 'LOW').length,
  },
}
