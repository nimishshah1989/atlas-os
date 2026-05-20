"""Policy module — effective-policy resolution and validation.

Public surface:
- ``Policy`` — frozen dataclass representing the merged effective policy
- ``effective_policy`` — load house default + portfolio override from DB and merge
- ``validate_policy`` — return list of human-readable violation strings
- ``_merge`` — pure merge function (exported for direct testing)
"""

from atlas.intelligence.policy.policy import (
    Policy,
    _merge,
    effective_policy,
    validate_policy,
)

__all__ = ["Policy", "_merge", "effective_policy", "validate_policy"]
