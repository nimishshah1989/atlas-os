"""Tests for the SP07 tool registry."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from atlas.agents.tools import TOOL_NAMES, build_registry
from atlas.agents.tools.registry import Tool


def test_tool_names_has_exactly_12() -> None:
    # 10 v1 tools + get_top_conviction (SP04 Stage 3) + get_tv_analysis (TV-07).
    assert len(TOOL_NAMES) == 12


def test_top_conviction_is_registered() -> None:
    assert "get_top_conviction" in TOOL_NAMES


def test_tv_analysis_is_registered() -> None:
    assert "get_tv_analysis" in TOOL_NAMES


def test_tool_names_are_unique() -> None:
    assert len(TOOL_NAMES) == len(set(TOOL_NAMES))


def test_build_registry_returns_one_entry_per_tool() -> None:
    engine = MagicMock()
    reg = build_registry(engine)
    assert set(reg.keys()) == set(TOOL_NAMES)
    for name, tool in reg.items():
        assert isinstance(tool, Tool)
        assert tool.name == name
        assert tool.description, f"tool {name} missing description"
        assert isinstance(tool.parameters, dict)
        assert callable(tool.fn)


def test_as_groq_tool_produces_valid_schema() -> None:
    engine = MagicMock()
    reg = build_registry(engine)
    for name, tool in reg.items():
        spec = tool.as_groq_tool()
        assert spec["type"] == "function"
        fn = spec["function"]
        assert fn["name"] == name
        assert fn["description"] == tool.description
        params = fn["parameters"]
        # JSON Schema basics
        assert params["type"] == "object"
        assert "properties" in params


def test_parameters_schema_lists_only_known_kwargs() -> None:
    """The parameters schema must list only kwargs that the bound fn accepts."""
    import inspect

    from atlas.agents.tools.registry import _FUNCTIONS

    for name, fn in _FUNCTIONS.items():
        sig = inspect.signature(fn)
        # engine is positional; everything else is keyword-only
        kwarg_names = {
            p.name for p in sig.parameters.values() if p.kind == inspect.Parameter.KEYWORD_ONLY
        }
        engine_mock = MagicMock()
        tool = build_registry(engine_mock)[name]
        prop_names = set(tool.parameters.get("properties", {}).keys())
        assert prop_names.issubset(kwarg_names), (
            f"tool {name}: schema property names {prop_names - kwarg_names} "
            f"are not real kwargs of {fn.__name__} ({kwarg_names})"
        )


def test_distribution_stats_rejects_non_whitelisted() -> None:
    """The whitelist guard must reject (table, column) pairs not in the set."""
    from atlas.agents.tools.atlas_queries import query_distribution_stats

    engine = MagicMock()
    with pytest.raises(ValueError, match="whitelist"):
        query_distribution_stats(
            engine,
            table="atlas_stock_metrics_daily",
            metric_column="some_random_column",
        )
    with pytest.raises(ValueError, match="whitelist"):
        query_distribution_stats(
            engine,
            table="some_random_table",
            metric_column="rs_pctile_3m",
        )


def test_recent_findings_rejects_invalid_severity() -> None:
    from atlas.agents.tools.atlas_queries import query_recent_findings

    engine = MagicMock()
    with pytest.raises(ValueError, match="severity"):
        query_recent_findings(engine, severity="P9", n=5)
