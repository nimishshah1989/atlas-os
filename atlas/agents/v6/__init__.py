"""v6 agent surface — LLM brief generator (#47).

Lifts the SP07 Hermes pattern (Groq Llama 3.3 70B + 4 specialists + SEBI
guard) into the v6 brief-generation surface. The v5 atlas.agents.* root
remains for the in-flight SP07 Hermes specialists; this v6 subpackage is
the post-cutover surface called from the daily inference cron and from
``/v1/recommendation/{iid}``.

Public API
==========

- :class:`BriefGenerationResult` — return contract from
  :func:`generate_brief`.
- :func:`generate_brief` — main entrypoint. Cache-then-Groq-then-fallback
  pipeline.
- :func:`invalidate_briefs_on_corp_action` — corp-action cron post-step
  hook per CONTEXT.md "Brief cache invalidation".
- :exc:`SEBIGuardTripped` — raised by :func:`sebi_guard.check_brief` when
  a forbidden phrase is detected.
- :exc:`ACLViolation` — raised by :func:`readonly_session._verify_query_allowlist`
  when a query references a disallowed table.
- :data:`MAX_CONCURRENT_GROQ_CALLS` — orchestrator-layer concurrency cap
  (eng review §4 Finding 4.C).

Boundary
========
This package may import from ``atlas.db``, ``atlas.config`` (shared
kernel) but NOT from other v6 bounded contexts (``atlas.features``,
``atlas.decisions``, etc.). Data exchange happens via the
``atlas_agent_readonly`` Postgres role + a small set of read-only SQL
queries.
"""

from __future__ import annotations

from atlas.agents.v6.brief_generator import (
    MAX_CONCURRENT_GROQ_CALLS,
    BriefGenerationResult,
    GroqClient,
    generate_brief,
    invalidate_briefs_on_corp_action,
)
from atlas.agents.v6.readonly_session import (
    ACL_ALLOWLIST,
    ACLViolation,
    open_readonly_session,
)
from atlas.agents.v6.sebi_guard import FORBIDDEN_PHRASES, SEBIGuardTripped, check_brief

__all__ = [
    "ACL_ALLOWLIST",
    "FORBIDDEN_PHRASES",
    "MAX_CONCURRENT_GROQ_CALLS",
    "ACLViolation",
    "BriefGenerationResult",
    "GroqClient",
    "SEBIGuardTripped",
    "check_brief",
    "generate_brief",
    "invalidate_briefs_on_corp_action",
    "open_readonly_session",
]
