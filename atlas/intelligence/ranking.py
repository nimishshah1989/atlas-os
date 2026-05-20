"""Hybrid rank + absolute-floor classifier. Ranks entities cross-sectionally
by score, assigns a label by percentile band, then caps the top label when
the entity fails an absolute floor. Guarantees a label spread — never collapses
to one constant label. Pure: no DB, no IO.

Degenerate cases (documented):
- Empty input → {}
- Single entity → percentile 0.0 (bottom band)
- Ties → broken by entity_id string order for determinism
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class RankConfig:
    """Configuration for hybrid_rank_labels.

    labels: ordered worst -> best.
    band_pcts: ascending cumulative percentile cut-points,
        length must equal len(labels) - 1.
    floor_label: the top label the floor can cap. Any entity assigned
        this label that fails floor_min is stepped down one label.
    floor_min: minimum floor-metric value required to hold floor_label.
    """

    labels: list[str]
    band_pcts: list[Decimal]
    floor_label: str
    floor_min: Decimal


def hybrid_rank_labels(
    scores: dict[str, Decimal],
    floor_values: dict[str, Decimal],
    cfg: RankConfig,
) -> dict[str, str]:
    """Return {entity_id: label}.

    Ranks entities cross-sectionally by score (ascending), assigns a label
    by percentile band, then caps the top label when floor_values[entity]
    is below cfg.floor_min.

    Args:
        scores: mapping of entity_id to numeric score. Higher = better rank.
        floor_values: mapping of entity_id to absolute floor metric. Missing
            keys are treated as floor failure (same as value < floor_min).
        cfg: band configuration, floor label, and floor threshold.

    Returns:
        Mapping of entity_id to assigned label. Empty if scores is empty.

    Notes:
        - Single entity always receives the bottom band label (pct = 0.0).
        - Ties in score are broken by entity_id (string ascending) for
          full determinism across repeated calls.
        - floor_label at index 0: stepping down is a no-op (stays at index 0).
    """
    if not scores:
        return {}

    n = len(scores)
    # Sort ascending by (score, entity_id) — entity_id as tie-breaker
    ordered = sorted(scores.items(), key=lambda kv: (kv[1], kv[0]))

    out: dict[str, str] = {}
    for idx, (eid, _score) in enumerate(ordered):
        # Percentile: 0.0 for singleton or bottom; 1.0 for top
        pct = Decimal(idx) / Decimal(n - 1) if n > 1 else Decimal(0)

        # Count how many cut-points pct meets or exceeds → band index
        band = sum(1 for cut in cfg.band_pcts if pct >= cut)
        label = cfg.labels[band]

        # Apply absolute floor gate on the top label only
        if label == cfg.floor_label:
            fv = floor_values.get(eid)
            if fv is None or fv < cfg.floor_min:
                floor_idx = cfg.labels.index(cfg.floor_label)
                label = cfg.labels[max(0, floor_idx - 1)]

        out[eid] = label

    return out
