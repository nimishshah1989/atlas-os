"""SP03: OpenBB query handler dispatch table.

Import ``HANDLER_DISPATCH`` from this module to get the mapping from intent key
to handler async generator callable.

Handler callables have signature::

    async def handle_*(engine: Engine, query_text: str) -> AsyncGenerator[dict, None]

``classify_intent()`` lives in ``handlers/router.py`` — a pure function with no
DB imports — so it can be unit-tested without touching SQLAlchemy.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Callable

from sqlalchemy.engine import Engine

from atlas.api.openbb.handlers.breakouts import handle_breakouts
from atlas.api.openbb.handlers.leaders import handle_leaders
from atlas.api.openbb.handlers.regime import handle_regime
from atlas.api.openbb.handlers.rotation import handle_rotation

# Dispatch table: intent key → handler callable.
# ``query.py`` imports this dict and calls
# ``HANDLER_DISPATCH[intent](engine, query_text)``.
HANDLER_DISPATCH: dict[str, Callable[[Engine, str], AsyncGenerator[dict, None]]] = {
    "regime": handle_regime,
    "leaders": handle_leaders,
    "rotation": handle_rotation,
    "breakouts": handle_breakouts,
}

__all__ = ["HANDLER_DISPATCH"]
