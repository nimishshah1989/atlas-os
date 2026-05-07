"""Atlas — Adaptive Technical Lens for Asset States.

Reads from JIP Data Core's ``public.de_*`` tables and writes to its own
``atlas`` schema. Per ``docs/01_BACKEND_ARCHITECTURE.md`` Section 1.

The package is laid out per architecture Section 11:

- ``atlas.universe``  — Layer 2 reference data (M1)
- ``atlas.compute``   — Layer 3 metric, state, and decision pipelines (M2-M5)
- ``atlas.validation`` — Five-tier validation framework
- ``atlas.orchestration`` — Pipeline runner, stage definitions, notifications
- ``atlas.api``       — Thin FastAPI serving layer (post-M5)
"""

__version__ = "0.1.0"
