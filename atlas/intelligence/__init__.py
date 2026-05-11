"""Atlas intelligence layer — graded signals, IC measurement, composites.

This bounded context produces measured, validated outputs from the
deterministic compute layer. It MUST NOT import from atlas.api or atlas.compute
internals — only from the shared kernel (atlas.db, atlas.config).

See docs/phase2/00-master-plan.html for the full Phase 2 design.
"""
