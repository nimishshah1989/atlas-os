"""Invoke validate_m{3,4,5}.py and persist results to atlas_validator_results.

Parses the validator output (the existing scripts print "Total checks run: N"
and "Failures: K" + a "RESULT: PASS" or "RESULT: FAIL" line). Stores the
first 100 failure labels into a JSONB summary so the dashboard can display
recent regressions without having to re-run.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.engine import Engine

from atlas.compute._session import open_compute_session
from atlas.db import get_engine
from atlas.health.runs import _git_sha, _hostname

log = structlog.get_logger()

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ValidatorResult:
    validator: str
    total_checks: int
    failures: int
    status: str
    failure_labels: list[str]
    raw_stdout: str


# Match "  FAIL  some/label/here: stored=...".
_FAIL_LINE = re.compile(r"^\s*FAIL\s+([^\s:]+):", re.MULTILINE)
_TOTAL_RE = re.compile(r"Total checks run:\s*(\d+)")
_FAIL_COUNT_RE = re.compile(r"Failures:\s*(\d+)")
_RESULT_RE = re.compile(r"RESULT:\s*(PASS|FAIL)")


def _parse(stdout: str, validator: str) -> ValidatorResult:
    total_match = _TOTAL_RE.search(stdout)
    fail_match = _FAIL_COUNT_RE.search(stdout)
    result_match = _RESULT_RE.search(stdout)

    total = int(total_match.group(1)) if total_match else 0
    fail_count = int(fail_match.group(1)) if fail_match else 0
    status = result_match.group(1) if result_match else ("PASS" if fail_count == 0 else "FAIL")

    labels = _FAIL_LINE.findall(stdout)[:100]
    return ValidatorResult(
        validator=validator,
        total_checks=total,
        failures=fail_count,
        status=status,
        failure_labels=labels,
        raw_stdout=stdout,
    )


def run_validator(validator: str) -> ValidatorResult:
    """Run scripts/validate_<validator>.py and parse stdout."""
    validator = validator.upper()
    script_map = {
        "M3": "validate_m3.py",
        "M4": "validate_m4.py",
        "M5": "validate_m5.py",
    }
    if validator not in script_map:
        raise ValueError(f"unknown validator {validator!r}")

    script_path = ROOT / "scripts" / script_map[validator]
    log.info("validator_run_start", validator=validator, script=str(script_path))

    proc = subprocess.run(  # noqa: S603
        [sys.executable, str(script_path)],
        capture_output=True,
        text=True,
        check=False,
        timeout=900,  # 15 min hard cap
    )
    stdout = proc.stdout + ("\n[stderr]\n" + proc.stderr if proc.stderr else "")
    return _parse(stdout, validator)


def write_result(
    result: ValidatorResult,
    *,
    engine: Engine | None = None,
) -> uuid.UUID:
    """Persist one row to atlas_validator_results."""
    eng = engine or get_engine()
    run_id = uuid.uuid4()
    summary: dict[str, Any] = {"failures": result.failure_labels}
    with open_compute_session(eng) as conn:
        conn.execute(
            text("""
                INSERT INTO atlas.atlas_validator_results (
                    run_id, validator, ran_at,
                    total_checks, failures, status,
                    failure_summary, host, git_sha
                ) VALUES (
                    :run_id, :validator, :ran_at,
                    :total_checks, :failures, :status,
                    :failure_summary, :host, :git_sha
                )
            """),
            {
                "run_id": str(run_id),
                "validator": result.validator,
                "ran_at": datetime.now(UTC),
                "total_checks": result.total_checks,
                "failures": result.failures,
                "status": result.status,
                "failure_summary": json.dumps(summary),
                "host": _hostname(),
                "git_sha": _git_sha(),
            },
        )
        conn.commit()
    log.info(
        "validator_result_written",
        validator=result.validator,
        status=result.status,
        failures=result.failures,
    )
    return run_id


def run_and_record(
    validator: str,
    *,
    engine: Engine | None = None,
) -> ValidatorResult:
    """Run + persist in one call. Used by health_check_daily orchestrator."""
    result = run_validator(validator)
    write_result(result, engine=engine)
    return result


__all__ = ["ValidatorResult", "run_and_record", "run_validator", "write_result"]
