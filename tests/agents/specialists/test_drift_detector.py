"""Tests for the Drift Detector specialist."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock

from atlas.agents.specialists.drift_detector import DriftDetector


def _mock_engine(summary_rows: list[dict], finding_rows: list[dict] | None = None) -> MagicMock:
    """Mock engine: fetchall returns ``summary_rows`` for both queries."""
    conn = MagicMock()
    finding_rows = finding_rows or []

    def _execute(sql, *args, **kwargs) -> MagicMock:
        text_sql = str(sql)
        result = MagicMock()
        mappings = MagicMock()
        if "GROUP BY severity" in text_sql:
            mappings.fetchall.return_value = summary_rows
            mappings.fetchone.return_value = summary_rows[0] if summary_rows else None
        else:
            mappings.fetchall.return_value = finding_rows
            mappings.fetchone.return_value = finding_rows[0] if finding_rows else None
        result.mappings.return_value = mappings
        return result

    conn.execute.side_effect = _execute
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value = conn
    return engine


def _mock_tool_call(name: str, args: dict, tc_id: str = "tc_1") -> MagicMock:
    tc = MagicMock()
    tc.id = tc_id
    tc.function = MagicMock()
    tc.function.name = name
    tc.function.arguments = json.dumps(args)
    return tc


def _mock_response(content: str | None, tool_calls: list | None = None) -> MagicMock:
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls
    choice = MagicMock()
    choice.message = msg
    response = MagicMock()
    response.choices = [choice]
    response.usage = MagicMock(prompt_tokens=150, completion_tokens=70)
    return response


def test_drift_detector_findings_present() -> None:
    summary_rows = [
        {"severity": "P0", "finding_class": "data_gap", "n": 3, "unresolved": 2},
        {"severity": "P1", "finding_class": "calc_error", "n": 5, "unresolved": 1},
    ]
    finding_rows = [
        {
            "finding_class": "data_gap",
            "severity": "P0",
            "surface": "atlas_stock_metrics_daily",
            "identifier": "TCS:2026-05-08",
            "expected_value": "not null",
            "actual_value": "null",
            "first_seen": datetime(2026, 5, 8, tzinfo=UTC),
            "last_seen": datetime(2026, 5, 12, tzinfo=UTC),
            "resolved_at": None,
        }
    ]
    engine = _mock_engine(summary_rows, finding_rows)
    client = MagicMock()
    final = (
        "The validator surfaces 8 findings over the last 7 days, of which 3 "
        "are P0. Findings cluster on atlas_stock_metrics_daily (data_gap). "
        "Data as of 2026-05-12."
    )
    client.chat.completions.create.side_effect = [
        _mock_response(None, [_mock_tool_call("get_finding_summary", {"n_days": 7})]),
        _mock_response(final),
    ]

    agent = DriftDetector()
    result = agent.invoke("Any anomalies today?", engine=engine, client=client)
    assert "P0" in result.narrative
    assert result.agent_name == "drift_detector"


def test_drift_detector_zero_findings_clean_path() -> None:
    engine = _mock_engine([], [])
    client = MagicMock()
    final = (
        "No anomalies detected in the last 7 days; data-integrity signals "
        "nominal across all validator scopes. Data as of 2026-05-12."
    )
    client.chat.completions.create.side_effect = [
        _mock_response(None, [_mock_tool_call("get_finding_summary", {"n_days": 7})]),
        _mock_response(final),
    ]

    agent = DriftDetector()
    result = agent.invoke("Any anomalies?", engine=engine, client=client)
    assert "no anomalies" in result.narrative.lower() or "nominal" in result.narrative.lower()
