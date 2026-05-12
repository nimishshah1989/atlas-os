"""SP07: CLI to invoke a specialist agent.

Usage::

    # List available agents.
    python scripts/run_agent.py --list-agents

    # Route the question to the right specialist automatically.
    python scripts/run_agent.py --agent auto \\
        --question "Which sectors are rotating into Leading?"

    # Force a specific specialist.
    python scripts/run_agent.py --agent regime_watcher \\
        --question "What is the current market regime?"

    # JSON output for tooling.
    python scripts/run_agent.py --agent sector_rotation \\
        --question "..." --json

    # Persist the invocation to atlas_agent_invocations (audit trail).
    python scripts/run_agent.py --agent sector_rotation \\
        --question "..." --persist

Exit codes:
    0 - success
    2 - invalid arguments / unknown agent
    4 - GROQ_API_KEY missing
    5 - SEBI compliance failure (banned word in output)
    6 - runtime error (Groq 5xx, DB unreachable, etc.)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path

import structlog

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from atlas.agents.specialists import (  # noqa: E402
    SEBIComplianceError,
    classify_specialist,
    get_specialist,
    invoke_routed,
    list_specialists,
)
from atlas.agents.specialists.base import AgentResult  # noqa: E402
from atlas.db import get_engine  # noqa: E402

log = structlog.get_logger()

_VALID_AGENTS = (
    "auto",
    "sector_rotation",
    "stock_screener",
    "regime_watcher",
    "drift_detector",
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Invoke an Atlas specialist agent from the command line."
    )
    p.add_argument(
        "--agent",
        choices=_VALID_AGENTS,
        default="auto",
        help="Which specialist to use. 'auto' routes by keyword.",
    )
    p.add_argument(
        "--question",
        type=str,
        default=None,
        help="The user question. Required unless --list-agents.",
    )
    p.add_argument(
        "--list-agents",
        action="store_true",
        help="Print the available specialists and exit.",
    )
    p.add_argument(
        "--json",
        action="store_true",
        help="Print the AgentResult as JSON to stdout.",
    )
    p.add_argument(
        "--persist",
        action="store_true",
        help="Write the invocation to atlas.atlas_agent_invocations.",
    )
    return p.parse_args(argv)


def _format_text(agent_name: str, result: AgentResult) -> str:
    """Pretty-print an AgentResult for the terminal."""
    pretty_name = agent_name.replace("_", " ").title()
    lines = [f"[{pretty_name}]", result.narrative.strip(), ""]
    if result.tool_calls:
        lines.append("Tool calls:")
        for tc in result.tool_calls:
            args_repr = ", ".join(f"{k}={v!r}" for k, v in tc.get("args", {}).items())
            keys = ", ".join(tc.get("result_keys", []) or [])
            lines.append(f"  - {tc['tool']}({args_repr}) -> [{keys}]")
        lines.append("")
    lines.append(
        f"Tokens: in={result.input_tokens} out={result.output_tokens}   "
        f"Iterations: {result.iterations}"
    )
    if result.data_as_of:
        lines.append(f"Data as of: {result.data_as_of.isoformat()}")
    return "\n".join(lines)


def _format_json(agent_name: str, result: AgentResult) -> str:
    payload = asdict(result)
    payload["routed_to"] = agent_name
    if result.data_as_of:
        payload["data_as_of"] = result.data_as_of.isoformat()
    return json.dumps(payload, indent=2, default=str)


def _persist(engine, agent_name: str, question: str, result: AgentResult) -> None:
    """Write the invocation to atlas_agent_invocations as caller='cli'."""
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO atlas.atlas_agent_invocations (
                    agent_name, question, narrative, tool_calls, model,
                    input_tokens, output_tokens, iterations, data_as_of,
                    caller, user_id
                ) VALUES (
                    :agent_name, :question, :narrative,
                    CAST(:tool_calls AS JSONB),
                    :model, :input_tokens, :output_tokens, :iterations,
                    :data_as_of, 'cli', NULL
                )
                """
            ),
            {
                "agent_name": agent_name,
                "question": question,
                "narrative": result.narrative,
                "tool_calls": json.dumps(result.tool_calls),
                "model": result.model,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "iterations": result.iterations,
                "data_as_of": result.data_as_of,
            },
        )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    if args.list_agents:
        print("Available specialists:")
        for s in list_specialists():
            print(f"  - {s['name']}: {s['description']}")
        return 0

    if not args.question or not args.question.strip():
        print(
            "error: --question is required (or pass --list-agents).",
            file=sys.stderr,
        )
        return 2

    if not os.environ.get("GROQ_API_KEY"):
        print(
            "error: GROQ_API_KEY is not set. Get one at console.groq.com.",
            file=sys.stderr,
        )
        return 4

    engine = get_engine()
    log.info(
        "run_agent_cli_start",
        agent=args.agent,
        persist=args.persist,
    )

    try:
        if args.agent == "auto":
            agent_name, result = invoke_routed(args.question, engine=engine)
        else:
            agent = get_specialist(args.agent)
            result = agent.invoke(args.question, engine=engine)
            agent_name = args.agent
    except SEBIComplianceError as exc:
        print(f"SEBI compliance error: {exc}", file=sys.stderr)
        return 5
    except KeyError as exc:
        print(f"unknown agent: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"runtime error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 6

    if args.agent == "auto":
        # Echo the routing decision for transparency.
        also_classified = classify_specialist(args.question)
        log.info("routed_to", agent=also_classified)

    if args.json:
        print(_format_json(agent_name, result))
    else:
        print(_format_text(agent_name, result))

    if args.persist:
        try:
            _persist(engine, agent_name, args.question, result)
            print("\nPersisted to atlas.atlas_agent_invocations.", file=sys.stderr)
        except Exception as exc:
            print(f"warning: persist failed: {exc}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
