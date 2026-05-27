"""Sector relative-strength panel helpers for deep-search v2.

Lifted from :mod:`/tmp/deep_search_v2/sector_rs_features.py` (staging
subagent), with the leave-one-out (LOO) fix applied to
:func:`sector_cohort_mean` per the integration plan's risk register
(self-reference bias when a stock is part of its own peer mean).

All helpers are pure functions over wide panels (date × iid). The
``df.T.groupby(labels).<op>().T`` idiom is the pandas 2.x compatible
alternative to ``groupby(axis=1)``.

Sector mapping is read from a CSV at module load time (provided by the
parallel staging subagent at ``/tmp/deep_search_v2/sector_mapping.csv``).
If absent, :func:`load_sector_mapping` returns ``None``; sector panels
then fall back to NaN-filled DataFrames and candidates that reference
them are filtered out at evaluation time.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd

# Path the parallel subagent staged sector mapping at.
DEFAULT_SECTOR_MAPPING_PATH = Path("/tmp/deep_search_v2/sector_mapping.csv")  # noqa: S108

# Minimum members per sector to compute statistics. Below this, LOO cohort
# means are degenerate (1 peer → division by 0 → NaN; 2 peers → noisy).
MIN_SECTOR_SIZE = 3


def load_sector_mapping(path: Path | None = None) -> pd.Series | None:
    """Load iid → sector mapping. Returns None if the file is unavailable.

    Args:
        path: optional override; defaults to
            :data:`DEFAULT_SECTOR_MAPPING_PATH`.

    Returns:
        Series indexed by iid (str), values are sector labels. ``None``
        when the mapping file is missing — callers MUST treat downstream
        sector panels as NaN and skip-eval candidates that reference them.
    """
    path = path if path is not None else DEFAULT_SECTOR_MAPPING_PATH
    if not path.exists():
        return None
    df = pd.read_csv(path)
    if "iid" not in df.columns or "sector" not in df.columns:
        return None
    df = df.drop_duplicates("iid").set_index("iid")
    # Coerce iids to string for safe pandas index intersection.
    df.index = df.index.astype(str)
    return cast(pd.Series, df["sector"].astype(str))


def sector_cohort_mean_loo(returns: pd.DataFrame, sector_of: pd.Series) -> pd.DataFrame:
    """Leave-one-out (LOO) cohort mean.

    For each (date, iid), returns the mean of all OTHER members of the
    same sector — i.e. excludes ``iid`` itself from its peer set. This
    avoids the self-reference bias the staged module had (cohort mean
    that includes self pulls sector_rs toward 0 for any single member).

    Implementation: ``(sector_sum - self) / (sector_count - 1)``. When
    the sector has ≤ 1 member at a given date, the result is NaN.

    Vectorised — no per-instrument loop.
    """
    cols = returns.columns.intersection(sector_of.index)
    r = returns[cols]
    sec_labels = sector_of.loc[cols]
    # Sector sum / count broadcasts back to per-iid columns via transform.
    sector_sum = r.T.groupby(sec_labels).transform("sum").T
    # Count of non-NaN members per sector per date.
    valid = (~r.isna()).astype(float)
    sector_count = valid.T.groupby(sec_labels).transform("sum").T
    # LOO numerator and denominator.
    # For NaN cells in r, sector_sum already excludes them; subtracting
    # NaN would propagate, so guard by filling self-NaN with 0.
    own = r.fillna(0.0)
    loo_num = sector_sum - own
    loo_den = sector_count - valid  # subtract 1 only if self was non-NaN
    loo_den = loo_den.where(loo_den >= 1, np.nan)
    out = loo_num / loo_den
    # Where the original was NaN, the LOO mean should still be defined
    # (peers exist independent of self being NaN). But where the sector
    # has only 1 valid member, loo_den is 0 → NaN already.
    return out


def within_sector_rank(returns: pd.DataFrame, sector_of: pd.Series) -> pd.DataFrame:
    """Percentile rank within sector (per row/date). Output in [0, 1] or NaN."""
    cols = returns.columns.intersection(sector_of.index)
    r = returns[cols]
    sec_labels = sector_of.loc[cols]
    return r.T.groupby(sec_labels).rank(pct=True).T


def sector_breadth(rs: pd.DataFrame, sector_of: pd.Series) -> pd.DataFrame:
    """Per-date per-sector: fraction of members with rs > 0."""
    cols = rs.columns.intersection(sector_of.index)
    r = rs[cols]
    sec_labels = sector_of.loc[cols]
    pos = (r > 0).astype(float)
    return pos.T.groupby(sec_labels).mean().T


def sector_median_return(returns: pd.DataFrame, sector_of: pd.Series) -> pd.DataFrame:
    """Per-date per-sector median formation return."""
    cols = returns.columns.intersection(sector_of.index)
    r = returns[cols]
    sec_labels = sector_of.loc[cols]
    return r.T.groupby(sec_labels).median().T


def sector_strength_rank(sector_med: pd.DataFrame) -> pd.DataFrame:
    """Rank sectors across each row; 1 = strongest median return."""
    return sector_med.rank(axis=1, ascending=False, method="min")


def sector_vol_regime_panel(vol: pd.DataFrame, sector_of: pd.Series) -> pd.DataFrame:
    """Per-date per-sector median realised volatility."""
    cols = vol.columns.intersection(sector_of.index)
    v = vol[cols]
    sec_labels = sector_of.loc[cols]
    return v.T.groupby(sec_labels).median().T


def broadcast_sector_to_iid(
    sec_panel: pd.DataFrame,
    iid_to_sector: pd.Series,
    template_columns: pd.Index,
) -> pd.DataFrame:
    """Broadcast a (date × sector) panel back to (date × iid).

    For each iid, picks the panel column matching its sector label. iids
    whose sector is absent from ``sec_panel`` (sector dropped for size, or
    iid missing from mapping) get NaN columns.
    """
    # iid -> sector lookup. For iids not in mapping (NaN sector), the
    # reindex below produces a NaN column key, which lookup converts to
    # an all-NaN column in the output.
    sector_for_each_iid = iid_to_sector.reindex(template_columns)
    out = pd.DataFrame(
        np.nan,
        index=sec_panel.index,
        columns=template_columns,
        dtype=float,
    )
    available_sectors = set(sec_panel.columns)
    for iid in template_columns:
        sec = sector_for_each_iid.loc[iid] if iid in sector_for_each_iid.index else None
        if sec is None or pd.isna(sec) or sec not in available_sectors:
            continue
        out[iid] = sec_panel[sec].values
    return out
