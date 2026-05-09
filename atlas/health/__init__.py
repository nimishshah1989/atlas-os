"""Backend data health observability — M12.

Operational table writes: atlas_pipeline_runs, atlas_validator_results,
atlas_health_daily. See docs/superpowers/specs/2026-05-09-atlas-m12-*.md.
"""

from atlas.health.runs import finish_run, record_run

__all__ = ["finish_run", "record_run"]
