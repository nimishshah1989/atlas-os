"""SP03: OpenBB query handler dispatch table.

Import ``HANDLER_DISPATCH`` from this module to get the mapping from intent key
to handler async generator callable.

Handler callables have signature::

    async def handle_*(engine: Engine, query_text: str) -> AsyncGenerator[dict, None]

Concrete handler modules (regime/leaders/rotation/breakouts) are imported and
the dispatch table is built in Task 6. This package marker is intentionally
minimal so ``handlers/router.py`` (the intent classifier — pure function, no
DB) can be unit-tested without dragging the SQLAlchemy-touching handlers in.
"""

from __future__ import annotations
