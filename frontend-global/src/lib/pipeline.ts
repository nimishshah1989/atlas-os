// src/lib/pipeline.ts — what runs, when, what it writes, and what it means when it does not.
//
// THE FM'S ASK. "The help part can't just have table names. It should have some understanding,
// properly written, of what that particular script was about or what that table was about… if
// it's green, yellow, or red, and within technicals, what needs to be run when." /health printed
// `script_name` and `table_name` and nothing else; this file is the understanding, in one place,
// so the health page, the freshness table and the methodology page all say the same thing about
// the same step.
//
// EVERY SENTENCE HERE IS FROM THE PRODUCER'S OWN DOCSTRING or the orchestrator's comments
// (scripts/ops/atlas_global_daily.sh, atlas_global_weekly.sh, scripts/global_market/*.py). It
// describes; it never restates a number — weights, floors and cut points live in
// atlas_global.atlas_thresholds and are read from there by the pages (rule #1).
//
// THE TWO SCHEDULES. The NIGHTLY runs at 01:00 UTC Tue–Sat (21:00 ET the previous evening, after
// extended hours), anchored on the last complete US session. The WEEKLY refreshes identity and
// the slow feeds. A failed step never aborts the chain; it is collected and reported. A failed GATE
// withholds publish: the board keeps its last-good data and the failure is pushed to Telegram.

export type Stage = 'identity' | 'ingest' | 'compute' | 'score' | 'gate' | 'publish'
export type Cadence = 'nightly' | 'weekly' | 'worker'

export type Step = {
  /** The step label the orchestrator records in atlas_pipeline_runs.script_name. */
  key: string
  script: string
  stage: Stage
  cadence: Cadence
  /** What it does, in the producer's own terms. */
  does: string
  /** The atlas_global tables it writes. */
  writes: string[]
  /** What the FM sees when it fails — the honest consequence, not the stack trace. */
  ifItFails: string
}

export const STAGE_LABEL: Record<Stage, string> = {
  identity: 'Identity — what exists',
  ingest: 'Ingest — the feeds',
  compute: 'Compute — the numbers behind every column',
  score: 'Score — lenses, groups, rankings, books',
  gate: 'Gates — nothing publishes past a red one',
  publish: 'Publish — the board advances',
}

export const STAGE_ORDER: Stage[] = ['identity', 'ingest', 'compute', 'score', 'gate', 'publish']

export const CADENCE_LABEL: Record<Cadence, string> = {
  nightly: 'nightly, 01:00 UTC Tue–Sat',
  weekly: 'weekly',
  worker: 'every 5 minutes',
}

export const STEPS: Step[] = [
  // ── weekly identity ──
  {
    key: 'build_identity',
    script: 'build_identity.py',
    stage: 'identity',
    cadence: 'weekly',
    does: 'Builds the instrument directory from the real listing files — Nasdaq Trader, the SEC ticker files, Tiingo — and records every symbol alias. The only writer of instrument_master.',
    writes: ['instrument_master', 'symbol_alias'],
    ifItFails: 'New listings and renamed tickers are missing until it runs again; everything already listed keeps working.',
  },
  {
    key: 'seed_benchmarks',
    script: 'seed_benchmarks.py',
    stage: 'identity',
    cadence: 'weekly',
    does: 'Registers the benchmarks every relative-strength figure is measured against (SPY first).',
    writes: ['benchmark_master'],
    ifItFails: 'Nothing changes unless a benchmark was added; the existing rows stand.',
  },
  {
    key: 'seed_taxonomy',
    script: 'seed_taxonomy.py',
    stage: 'identity',
    cadence: 'weekly',
    does: 'Seeds the sector and theme taxonomy the classifier files funds under.',
    writes: ['taxonomy_sector'],
    ifItFails: 'A new theme is not filed until it runs; existing themes keep their funds.',
  },
  {
    key: 'ingest_index_membership',
    script: 'ingest_index_membership.py',
    stage: 'identity',
    cadence: 'weekly',
    does: 'Reads the S&P 500 constituents from the issuer’s holdings workbooks (SPY and the eleven sector SPDRs) into a dated membership journal, and stamps each member’s GICS sector.',
    writes: ['index_membership', 'instrument_master.sector_gics'],
    ifItFails: 'Index changes since the last run are not reflected: a company added to the index is not yet scored, one removed is still ranked.',
  },
  {
    key: 'ingest_nport',
    script: 'ingest_nport.py',
    stage: 'ingest',
    cadence: 'weekly',
    does: 'Reads each fund’s Form N-PORT filing from the SEC: what it holds and what those holdings are worth. Fills fund assets (AUM); carries no expense ratio and no shares outstanding, which is why those still wait on an issuer feed.',
    writes: ['etf_holdings', 'etf_meta'],
    ifItFails: 'Holdings and assets go stale by a week. Concentration, look-through and the Assets column stop moving; nothing invents a value in the meantime.',
  },
  // ── nightly ingest ──
  {
    key: 'ingest_prices',
    script: 'ingest_prices.py',
    stage: 'ingest',
    cadence: 'nightly',
    does: 'Pulls the session’s bars on three adjustment bases — raw (what traded, the only comparable volume), split-adjusted (the chart and the technicals) and total-return (the marks and every return) — plus corporate actions.',
    writes: ['ohlcv_daily', 'corporate_actions'],
    ifItFails: 'Nothing downstream has a new session to compute on. The board shows the previous session and the as-of stamp says so.',
  },
  {
    key: 'ingest_macro',
    script: 'ingest_macro.py',
    stage: 'ingest',
    cadence: 'nightly',
    does: 'FRED’s daily series — the S&P price index (the cross-check for SPY’s bars, never a shown price), VIX, the 10-year, the 3-month bill (the risk-free rate every Sharpe uses) and the broad dollar.',
    writes: ['macro_daily'],
    ifItFails: 'The Pulse backdrop and the Sharpe/Sortino risk-free leg use the last day on file.',
  },
  {
    key: 'ingest_financials',
    script: 'ingest_financials.py',
    stage: 'ingest',
    cadence: 'nightly',
    does: 'SEC XBRL company facts, kept point-in-time: a restated quarter arrives as a new row with its own filing date and the original is never touched, so a backtest reads what the market actually knew.',
    writes: ['stock_financials_pit'],
    ifItFails: 'The fundamental lens scores on the last filings on file; a company that reported today is scored on its previous quarter until the next run.',
  },
  {
    key: 'ingest_filings_8k',
    script: 'ingest_filings_8k.py',
    stage: 'ingest',
    cadence: 'nightly',
    does: 'Every 8-K per registrant, keyed by accession number, with the item codes the registrant itself put on the form. The catalyst lens reads those codes and never a headline.',
    writes: ['filings_8k'],
    ifItFails: 'Today’s filings are missing from the catalyst lens until the next run; nothing older changes.',
  },
  {
    key: 'ingest_short_interest',
    script: 'ingest_short_interest.py',
    stage: 'ingest',
    cadence: 'nightly',
    does: 'FINRA’s consolidated short interest, one settlement at a time (twice a month). The stock flow lens’s feed.',
    writes: ['short_interest'],
    ifItFails: 'The flow lens carries the last settlement; a new settlement day is picked up on the next run.',
  },
  // ── compute ──
  {
    key: 'compute_technicals',
    script: 'compute_technicals.py',
    stage: 'compute',
    cadence: 'nightly',
    does: 'Every number in technical_daily for every active fund and every index member: EMAs and the above-flags, RSI, ATR, Bollinger width, 52-week position, calendar-anchored returns, relative strength against SPY in the relative form, volatility, drawdown, beta, Sharpe, Sortino, Calmar and the traded-value window.',
    writes: ['technical_daily'],
    ifItFails: 'No score can be built for the session (the scorers read this table), and the board’s price columns stay on the previous session.',
  },
  {
    key: 'build_universe_snapshot',
    script: 'build_universe_snapshot.py',
    stage: 'compute',
    cadence: 'nightly',
    does: 'One row per active instrument per session saying whether the FM’s rules offer it — above the liquidity floor, a current index member for stocks, neither leveraged nor inverse for funds — with the traded value that decided it and the one reason when it is out.',
    writes: ['universe_snapshot'],
    ifItFails: 'The board opens on the previous session’s universe. If the floor is unset the step exits without writing and gate A says so.',
  },
  // ── score ──
  {
    key: 'score_stocks',
    script: 'score_stocks.py',
    stage: 'score',
    cadence: 'nightly',
    does: 'Scores every in-universe S&P 500 member on its lenses and ranks it inside its SPY-weight cohort. Counts and names the members it could not score, so “503 members, 470 scored” is a printed number, never a silently smaller denominator.',
    writes: ['lens_scores_daily'],
    ifItFails: 'The S&P board shows the last scored session and says which session that was.',
  },
  {
    key: 'build_exposures',
    script: 'build_exposures.py',
    stage: 'score',
    cadence: 'nightly',
    does: 'Turns a fund’s holdings list into what it means: top-ten concentration and the country and sector evidence the classifier and the cost lens read. Keyed by the holdings’ own date, because exposures only change when holdings do.',
    writes: ['etf_exposure_daily'],
    ifItFails: 'The concentration sub-score and the look-through gate read the last computed snapshot.',
  },
  {
    key: 'classify_etfs',
    script: 'classify_etfs.py',
    stage: 'score',
    cadence: 'nightly',
    does: 'Writes down what a fund’s own registered name says it does — asset class, strategy, theme, country, leveraged or inverse — with the rule that fired and the words it matched. The peer group every ETF is ranked inside comes from here; a name no rule reads is marked Unclassified rather than filed somewhere plausible.',
    writes: ['etf_classification'],
    ifItFails: 'Funds keep their previous classification; a newly listed fund has none and is ranked as Unclassified.',
  },
  {
    key: 'score_etfs',
    script: 'score_etfs.py',
    stage: 'score',
    cadence: 'nightly',
    does: 'Scores every ETF on the lenses that have inputs and ranks it inside its peer group (asset class × strategy). A lens with no data is absent, never zero; the row records how many lenses the composite was built from, and the board prints it beside every score.',
    writes: ['etf_scores_daily'],
    ifItFails: 'The ETF board shows the last scored session and says which session that was.',
  },
  {
    key: 'build_country_views',
    script: 'build_country_views.py',
    stage: 'score',
    cadence: 'nightly',
    does: 'One representative fund per country — unhedged, ungeared, largest by assets among the funds whose names say the market — and its relative strength against SPY over six windows. The Countries page.',
    writes: ['country', 'country_daily'],
    ifItFails: 'The Countries grid stays on the previous session.',
  },
  {
    key: 'mark_baskets',
    script: 'mark_baskets.py',
    stage: 'score',
    cadence: 'nightly',
    does: 'Books a new basket once (one buy per name at the last real close, fractional shares, cost from the thresholds) and re-marks every basket’s whole NAV history from its trades and the bars, so a vendor revision is honoured and a re-run writes identical rows. The 5-minute worker runs the same script for baskets with no NAV yet.',
    writes: ['basket_trades', 'basket_nav_daily'],
    ifItFails: 'Baskets show their last mark; a basket saved today waits for the worker. A basket the marker refuses (a name with no recent print, a weight outside the thresholds) is named in the run’s report.',
  },
  // ── gates ──
  {
    key: 'validate_global_BASIS',
    script: 'validate_global.py --check BASIS',
    stage: 'gate',
    cadence: 'nightly',
    does: 'Measures which price series the close column actually carries, against FRED’s S&P index as an independent witness: the correlation, the drift of the level ratio, and the dividend-sized excess that separates total return from split-only. Fails rather than guesses when the evidence names neither.',
    writes: [],
    ifItFails: 'Publish is withheld. Every return on the board divides by this series; if its basis is in doubt the previous session stays up.',
  },
  {
    key: 'freshness_guard',
    script: 'freshness_guard.py',
    stage: 'gate',
    cadence: 'nightly',
    does: 'Every table the board reads must be within its tolerance, counted in SPY sessions, and every one of them must name a producer wired into an orchestrator. A fresh date over a collapsed row count is caught too — an incomplete ingest is not a fresh one.',
    writes: [],
    ifItFails: 'Publish is withheld and the failing table is named. The board keeps its last-good data.',
  },
  {
    key: 'validate_global_A',
    script: 'validate_global.py --check A',
    stage: 'gate',
    cadence: 'nightly',
    does: 'The price spine, over the scored universe: the anchor session exists, completeness against the previous session, impossible daily moves, split-sized jumps with no corporate action on record, the re-basing seam, and the session’s returns against FRED. Geared funds and sub-floor shells are excluded by construction and counted, so a real defect in a scored name cannot hide.',
    writes: [],
    ifItFails: 'Publish is withheld. A large move with no action on record is exactly the kind of row that would otherwise reach the board as a 30,000 percent volatility.',
  },
  {
    key: 'validate_global_C',
    script: 'validate_global.py --check C',
    stage: 'gate',
    cadence: 'nightly',
    does: 'The scores are usable, on produced rows: the composite and each lens spread out rather than clustering on one value (a table seeded with zeros scores everyone 61), every scored row has a peer group, and the tier ladder’s minimum-lens rule held.',
    writes: [],
    ifItFails: 'Publish is withheld. A scorer that ran is not a scorer that worked, and the previous session’s ranking stays up.',
  },
  {
    key: 'validate_baskets',
    script: 'validate_baskets.py',
    stage: 'gate',
    cadence: 'nightly',
    does: 'Every basket’s book, independently of the marker: a NAV row at the anchor, cash plus positions reconciling to the NAV within a cent, every trade priced at the stored close of its date, target weights summing to one.',
    writes: [],
    ifItFails: 'Publish is withheld and the basket and check are named.',
  },
  // ── publish ──
  {
    key: 'publish',
    script: 'POST /api/revalidate',
    stage: 'publish',
    cadence: 'nightly',
    does: 'One request to the board with the tag every cached read carries, so the next visit reads the new session. Fired only when every gate passed.',
    writes: [],
    ifItFails: 'The data is in the database and the board has not been told. The stamp in the top bar keeps the previous session until the next successful publish.',
  },
  {
    key: 'write_health_snapshot',
    script: 'write_health_snapshot.py',
    stage: 'publish',
    cadence: 'nightly',
    does: 'Writes this page: one row per step from the run, the validators’ verdicts, and each table’s lag in SPY sessions from a live count. Runs even when a gate failed.',
    writes: ['atlas_pipeline_runs', 'atlas_validator_results', 'atlas_health_daily'],
    ifItFails: 'This page is a run behind; the board itself is unaffected.',
  },
]

export const STEP_BY_KEY: Record<string, Step> = Object.fromEntries(STEPS.map((s) => [s.key, s]))

/** What each served table holds — the freshness table's "what this is" column. The producer is
 *  scripts/global_market/freshness_guard.py's PRODUCERS registry, restated as a step key. */
export const TABLES: Record<string, { holds: string; step: string }> = {
  instrument_master: { holds: 'The directory: every listed instrument, its class, its exchange, whether it is active.', step: 'build_identity' },
  ohlcv_daily: { holds: 'Daily bars on three bases — raw, split-adjusted, total-return.', step: 'ingest_prices' },
  macro_daily: { holds: 'FRED’s daily series: the S&P price index, VIX, yields, the dollar.', step: 'ingest_macro' },
  index_membership: { holds: 'Who was in the S&P 500 on which dates.', step: 'ingest_index_membership' },
  universe_snapshot: { holds: 'Per session, whether the FM’s rules offer each instrument, and why not.', step: 'build_universe_snapshot' },
  technical_daily: { holds: 'Every technical, return, relative-strength and risk number per instrument per session.', step: 'compute_technicals' },
  country_daily: { holds: 'Each country’s representative fund and its relative strength, per session.', step: 'build_country_views' },
  etf_classification: { holds: 'What each fund does, from its name: class, strategy, theme, country, gearing.', step: 'classify_etfs' },
  etf_scores_daily: { holds: 'Every ETF’s lenses, composite, tier and peer group, per session.', step: 'score_etfs' },
  lens_scores_daily: { holds: 'Every S&P 500 member’s lenses, composite, tier and cohort, per session.', step: 'score_stocks' },
  basket_nav_daily: { holds: 'Every basket’s NAV, cash and position count, per session, replayed from its trades.', step: 'mark_baskets' },
  stock_financials_pit: { holds: 'Company financials as filed, point-in-time, restatements as new rows.', step: 'ingest_financials' },
  etf_holdings: { holds: 'What each fund holds, from its N-PORT filing.', step: 'ingest_nport' },
  etf_meta: { holds: 'Fund facts from the filing: assets under management and its date.', step: 'ingest_nport' },
  etf_exposure_daily: { holds: 'What the holdings mean: top-ten weight, country and sector exposure.', step: 'build_exposures' },
  filings_8k: { holds: 'Every 8-K per registrant with the item codes on the form.', step: 'ingest_filings_8k' },
  short_interest: { holds: 'FINRA’s consolidated short interest per settlement.', step: 'ingest_short_interest' },
}

/** The RAG a step shows on the help page. Red is a failure; amber is a step that has not run in
 *  the window its cadence implies, or is mid-run; green is a success inside that window; grey is
 *  a step that has never recorded a run. The window is one cadence plus a night's slack — an ops
 *  display convention, not a methodology number. */
export type Rag = 'green' | 'amber' | 'red' | 'grey'

const WINDOW_HOURS: Record<Cadence, number> = { nightly: 30, weekly: 8 * 24, worker: 30 }

export function stepRag(
  step: Step,
  run: { status: string; ended_at: Date | null; started_at: Date } | undefined,
  now: Date,
): Rag {
  if (!run) return 'grey'
  if (run.status === 'failed') return 'red'
  if (run.status === 'running' || run.status === 'queued') return 'amber'
  const ended = run.ended_at ?? run.started_at
  const ageHours = (now.getTime() - ended.getTime()) / 3_600_000
  return ageHours <= WINDOW_HOURS[step.cadence] ? 'green' : 'amber'
}
