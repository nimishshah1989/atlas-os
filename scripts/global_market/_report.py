"""The per-outcome CSV report every global ingest script writes — the 'never silent' artefact.

One row per outcome (a ticker resolved or not, a member without a sector, an archive member
imported or refused …), a header naming the columns, and ``counts`` — a Counter keyed by the
``count_by`` columns joined with ``:`` — for the printed summary. Without a path nothing is
written but the counts still accumulate, so a script can always print how many of what.

    report = Report(path, ("pass", "ticker", "instrument_id", "status", "detail"),
                    count_by=("pass", "status"))
    report.add("current", "NVDA", iid, "resolved", "symbol")   # counts["current:resolved"] += 1
    report.close()

``import_stooq.Report`` (columns ``stooq_ticker, symbol, kind, exchange, status, rows,
detail``, counted by ``status``: imported / empty / unmapped / refused_bar / skipped_resumed)
and ``build_identity``'s writer fit the same shape with the default ``count_by=("status",)``.
"""

from __future__ import annotations

import csv
from collections import Counter
from collections.abc import Sequence
from pathlib import Path


class Report:
    def __init__(
        self, path: Path | None, columns: Sequence[str], count_by: Sequence[str] = ("status",)
    ) -> None:
        self.path = path
        self.columns = tuple(columns)
        self.counts: Counter[str] = Counter()
        self._count_at = [self.columns.index(c) for c in count_by]
        self._fh = path.open("w", newline="") if path else None
        self._w = csv.writer(self._fh) if self._fh else None
        if self._w:
            self._w.writerow(self.columns)

    def add(self, *row: object) -> None:
        """One outcome, positionally in column order (``None`` is written as an empty cell)."""
        if len(row) != len(self.columns):
            raise ValueError(f"report row has {len(row)} values for {len(self.columns)} columns")
        self.counts[":".join(str(row[i]) for i in self._count_at)] += 1
        if self._w:
            self._w.writerow(["" if v is None else v for v in row])

    def where(self) -> str:
        """The summary's pointer to the rows: the file, or how to get one."""
        return f"— listed in {self.path}" if self.path else "— pass --report to list them"

    def close(self) -> None:
        if self._fh:
            self._fh.close()
