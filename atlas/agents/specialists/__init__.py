"""SP07: research-focused specialist agents over Atlas data.

Public surface:
- ``SpecialistAgent`` — ABC for all specialists.
- ``AgentResult`` — frozen dataclass for one invocation result.
- ``SEBIComplianceError`` — raised when the final narrative trips the
  banned-word scan.
- ``get_specialist(name)`` — returns the instantiated specialist by name.
- ``classify_specialist(question)`` — keyword router.
- ``invoke_routed(question, *, engine, client=None)`` — route + invoke.

The four v1 specialists (sector_rotation, stock_screener, regime_watcher,
drift_detector) are registered eagerly at import time.
"""

from atlas.agents.specialists.base import (
    AgentResult,
    SEBIComplianceError,
    SpecialistAgent,
)
from atlas.agents.specialists.orchestrator import (
    SPECIALISTS,
    classify_specialist,
    get_specialist,
    invoke_routed,
    list_specialists,
)

__all__ = [
    "SPECIALISTS",
    "AgentResult",
    "SEBIComplianceError",
    "SpecialistAgent",
    "classify_specialist",
    "get_specialist",
    "invoke_routed",
    "list_specialists",
]
