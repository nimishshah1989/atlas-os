"""Atlas-M2 Tier 2 + Tier 3 validation runner.

Runs the hand-validation tiers and writes:

* ``docs/validation/m2_tier2_<date>.csv`` — per-metric hand vs prod comparison
* ``docs/validation/m2_tier3_<date>.csv`` — per-state hand vs prod comparison
* ``docs/validation/validation_M2_<date>.md`` — summary report

Per validation framework §3 (Tier 2: 15 stocks × 5 dates × metrics) and
§4 (Tier 3: 30 stocks × 4 states).

Usage::

    python scripts/m2_validate.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import structlog

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.db import get_engine  # noqa: E402
from atlas.validation.tier2_metrics import run_tier2  # noqa: E402
from atlas.validation.tier3_states import run_tier3  # noqa: E402

log = structlog.get_logger()


def main() -> int:
    today = date.today()
    out_dir = ROOT / "docs" / "validation"
    out_dir.mkdir(parents=True, exist_ok=True)

    engine = get_engine()

    print("[Tier 2] Running 15 stocks × 5 dates × metrics...")
    t2 = run_tier2(engine, milestone="M2", n_stocks=15, n_dates=5)
    t2_path = out_dir / f"m2_tier2_{today.isoformat()}.csv"
    t2.to_csv(t2_path, index=False)
    t2_pass = float(t2["pass"].mean()) if not t2.empty else 0.0
    print(f"[Tier 2] {len(t2)} checks, pass rate = {t2_pass:.2%} → {t2_path}")

    print("[Tier 3] Running 30 stocks × 4 state types...")
    # Find a recent date with state rows so we don't pick a non-trading day
    from sqlalchemy import text

    from atlas.compute._session import open_compute_session

    with open_compute_session(engine) as conn:
        last_date_row = conn.execute(
            text("SELECT MAX(date) FROM atlas.atlas_stock_states_daily")
        ).first()
        last_date = last_date_row[0] if last_date_row else today

    t3 = run_tier3(engine, target_date=last_date, milestone="M2", n_stocks=30)
    t3_path = out_dir / f"m2_tier3_{today.isoformat()}.csv"
    t3.to_csv(t3_path, index=False)
    t3_pass = float(t3["pass"].mean()) if not t3.empty else 0.0
    print(f"[Tier 3] {len(t3)} checks, pass rate = {t3_pass:.2%} → {t3_path}")

    # Summary report
    summary_path = out_dir / f"validation_M2_{today.isoformat()}.md"
    with open(summary_path, "w") as f:
        f.write(f"# Atlas-M2 Validation — {today.isoformat()}\n\n")
        f.write("## Tier 2 — Hand-computed metric checks\n\n")
        f.write(f"- Total checks: **{len(t2)}**\n")
        f.write(f"- Pass rate: **{t2_pass:.2%}**\n")
        f.write(f"- Detail: [`{t2_path.name}`](./{t2_path.name})\n\n")
        if t2_pass < 1.0 and not t2.empty:
            failed = t2[~t2["pass"]]
            f.write(f"### Failures ({len(failed)})\n\n")
            f.write("| instrument_id | date | metric | hand | prod | deviation |\n")
            f.write("|---|---|---|---|---|---|\n")
            for _, r in failed.head(20).iterrows():
                f.write(
                    f"| {r['instrument_id']} | {r['date']} | {r['metric']} | "
                    f"{r['hand']} | {r['prod']} | {r['deviation']} |\n"
                )
            f.write("\n")

        f.write("## Tier 3 — Hand-classified state checks\n\n")
        f.write(f"- Total checks: **{len(t3)}**\n")
        f.write(f"- Pass rate: **{t3_pass:.2%}**\n")
        f.write(f"- Sample date: {last_date}\n")
        f.write(f"- Detail: [`{t3_path.name}`](./{t3_path.name})\n\n")
        if t3_pass < 1.0 and not t3.empty:
            failed = t3[~t3["pass"]]
            f.write(f"### Failures ({len(failed)})\n\n")
            f.write("| instrument_id | state_type | hand | prod |\n")
            f.write("|---|---|---|---|\n")
            for _, r in failed.head(20).iterrows():
                f.write(
                    f"| {r['instrument_id']} | {r['state_type']} | {r['hand']} | {r['prod']} |\n"
                )
            f.write("\n")

        verdict = "PASS" if t2_pass == 1.0 and t3_pass == 1.0 else "FAIL"
        f.write(f"## Verdict: **{verdict}**\n")

    print(f"\nSummary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
