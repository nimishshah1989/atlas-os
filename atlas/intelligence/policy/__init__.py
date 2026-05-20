"""Policy module — effective-policy resolution, validation, sector targets, and entry filter.

Public surface:
- ``Policy`` — frozen dataclass representing the merged effective policy
- ``effective_policy`` — load house default + portfolio override from DB and merge
- ``validate_policy`` — return list of human-readable violation strings
- ``_merge`` — pure merge function (exported for direct testing)
- ``SectorSignal`` — per-sector bottom-up signal (pct_stage_2, mean_within_state_rank)
- ``SectorTarget`` — per-sector derived target (sector, current, target, gap)
- ``derive_sector_targets`` — pure formula: engine signal ∩ policy cap ∩ regime cap
- ``CandidateInstrument`` — instrument with state/rank fields for entry filtering
- ``apply_entry_filter`` — pure filter: buy_states ∩ rank thresholds
- ``PositionSizeResult`` — result of the position-sizing formula (suggested_pct, binding_constraint)
- ``suggest_position_size`` — pure formula: target_gap ∩ max_per_stock ∩ regime_room
"""

from atlas.intelligence.policy.entry_filter import (
    CandidateInstrument,
    apply_entry_filter,
)
from atlas.intelligence.policy.policy import (
    Policy,
    _merge,
    effective_policy,
    validate_policy,
)
from atlas.intelligence.policy.sizing import (
    PositionSizeResult,
    suggest_position_size,
)
from atlas.intelligence.policy.targets import (
    SectorSignal,
    SectorTarget,
    derive_sector_targets,
)

__all__ = [
    "Policy",
    "_merge",
    "effective_policy",
    "validate_policy",
    "SectorSignal",
    "SectorTarget",
    "derive_sector_targets",
    "CandidateInstrument",
    "apply_entry_filter",
    "PositionSizeResult",
    "suggest_position_size",
]
