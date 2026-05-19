"""HRP portfolio construction — López de Prado 2016.

Three steps per spec §6.5:
  1. corr → distance: dist = sqrt(0.5 × (1 - corr))
  2. scipy.cluster.hierarchy.linkage(dist_condensed, method='single')
  3. Recursive bisection by inverse cluster-variance

Cap stack applied in order per spec §6.5:
  a. Single-name cap  (5%)
  b. Sector cap       (25%)
  c. Issuer-group cap (5%)
  d. Weight floor — drop names < 0.5%, re-normalize

Excess from a binding cap redistributes WITHIN THE SAME HRP CLUSTER when
possible; falls back to all uncapped names portfolio-wide.

Cap convergence algorithm:
  Each cap type uses a clamp-then-redistribute pass that is sum-preserving:
  the excess removed from violators is added to recipients in the same step,
  so sum(weights) stays at 1.0. No intermediate normalization is applied.
  The outer loop retries all three cap types until none fires (max 50 rounds).
  After the cap stack, a final normalization corrects any floating-point drift,
  then the weight floor is applied.

No DB access. Float weights are appropriate (dimensionless fractions, not money).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import scipy.cluster.hierarchy as sch
import scipy.spatial.distance as ssd
import structlog

log = structlog.get_logger()

__all__ = ["HrpAllocator", "HrpResult"]


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HrpResult:
    weights: pd.Series  # indexed by instrument_id, sums to 1.0
    cluster_assignment: dict[uuid.UUID, str]  # 'C1', 'C2', ...
    caps_binding: list[str]  # which caps bound: 'name', 'sector', 'group'
    dropped_below_floor: list[uuid.UUID]


# ---------------------------------------------------------------------------
# Internal helpers — HRP core
# ---------------------------------------------------------------------------


def _cluster_variance(cov: pd.DataFrame, cluster_items: list[Any]) -> float:
    """Inverse-variance-weighted cluster variance (López de Prado 2016)."""
    diag_var = np.diag(cov.loc[cluster_items, cluster_items].values)
    positive = diag_var[diag_var > 0]
    if len(positive) == 0:
        return 0.0
    safe_var = np.where(diag_var > 0, diag_var, positive.min() * 1e-6)
    inv_var = 1.0 / safe_var
    w = inv_var / inv_var.sum()
    sub_cov = cov.loc[cluster_items, cluster_items].values
    return float(w @ sub_cov @ w)


def _quasi_diagonalize(linkage_matrix: np.ndarray, n_items: int) -> list[int]:
    """Return leaf order following the dendrogram (quasi-diagonalization)."""
    clusters: dict[int, list[int]] = {i: [i] for i in range(n_items)}
    for idx, row in enumerate(linkage_matrix):
        left, right = int(row[0]), int(row[1])
        new_id = n_items + idx
        clusters[new_id] = clusters[left] + clusters[right]
    root_id = n_items + len(linkage_matrix) - 1
    return clusters[root_id]


def _recursive_bisection(cov: pd.DataFrame, items_sorted: list[Any]) -> pd.Series:
    """Allocate weights by recursive bisection on sorted cluster items."""
    weights = pd.Series(1.0, index=items_sorted)
    clusters: list[list[Any]] = [items_sorted]

    while clusters:
        new_clusters: list[list[Any]] = []
        for cluster in clusters:
            if len(cluster) <= 1:
                continue
            mid = len(cluster) // 2
            left, right = cluster[:mid], cluster[mid:]
            v_l = _cluster_variance(cov, left)
            v_r = _cluster_variance(cov, right)
            total = v_l + v_r
            if total == 0.0:
                alpha = 0.5
            else:
                alpha = 1.0 - v_l / total
            weights[left] *= alpha
            weights[right] *= 1.0 - alpha
            new_clusters.extend([left, right])
        clusters = new_clusters

    return weights


def _assign_clusters(
    linkage_matrix: np.ndarray,
    ids: list[Any],
    n_clusters: int,
) -> dict[Any, str]:
    """Assign cluster labels 'C1', 'C2', ... via fcluster maxclust criterion."""
    n = len(ids)
    if n <= 1:
        return {ids[0]: "C1"} if n == 1 else {}
    k = min(n_clusters, n)
    labels = sch.fcluster(linkage_matrix, t=k, criterion="maxclust")
    return {ids[i]: f"C{labels[i]}" for i in range(n)}


# ---------------------------------------------------------------------------
# Cap helpers — sum-preserving: redistribute excess without normalization
# ---------------------------------------------------------------------------


def _redistribute(
    w: pd.Series,
    excess: float,
    source_id: Any,
    cluster_assignment: dict[Any, str],
    exclude_ids: set[Any],
    per_name_cap: float,
) -> None:
    """Add `excess` to eligible recipients (in-place, sum-preserving).

    Priority: same-cluster names below per_name_cap, then all names below cap,
    excluding `exclude_ids` (already-capped names for this group/name).
    """
    cluster = cluster_assignment.get(source_id, "C0")
    same_cluster = [
        i
        for i in w.index
        if i not in exclude_ids
        and cluster_assignment.get(i, "C0") == cluster
        and w[i] < per_name_cap - 1e-10
    ]
    fallback = [i for i in w.index if i not in exclude_ids and w[i] < per_name_cap - 1e-10]
    eligible = same_cluster if same_cluster else fallback
    if not eligible:
        # Nowhere feasible — distribute to all non-excluded
        eligible = [i for i in w.index if i not in exclude_ids]
    if not eligible:
        return
    sub_total = sum(w[r] for r in eligible)
    if sub_total > 1e-14:
        for r in eligible:
            w[r] += excess * (w[r] / sub_total)
    else:
        share = excess / len(eligible)
        for r in eligible:
            w[r] += share


def _clamp_name(
    w: pd.Series,
    per_name_cap: float,
    cluster_assignment: dict[Any, str],
) -> bool:
    """One pass: clamp all names > per_name_cap, redistribute excess.

    Sum-preserving: total excess removed == total excess added.
    Returns True if any clamp happened.
    """
    over = w[w > per_name_cap + 1e-10].index.tolist()
    if not over:
        return False

    over_set = set(over)
    for iid in over:
        excess = w[iid] - per_name_cap
        w[iid] = per_name_cap
        _redistribute(w, excess, iid, cluster_assignment, over_set, per_name_cap)

    return True


def _clamp_group(
    w: pd.Series,
    group_map: dict[Any, str],
    group_cap: float,
    cluster_assignment: dict[Any, str],
    per_name_cap: float,
    pinned_ids: set[Any] | None = None,
) -> tuple[bool, set[Any]]:
    """One pass: clamp ALL groups > group_cap simultaneously, redistribute excess.

    Simultaneous approach: collect all violations, clamp all at once, then
    redistribute all excess to names NOT in any capped group and NOT in pinned_ids
    (previously-capped-group members from prior passes). This prevents cascading
    ping-pong between sectors/groups.

    Sum-preserving. Returns (cap_bound, new_pinned_ids).
    """
    if pinned_ids is None:
        pinned_ids = set()

    # Build group membership
    group_members: dict[str, list[Any]] = {}
    for iid in w.index:
        g = group_map.get(iid, str(iid))
        group_members.setdefault(g, []).append(iid)

    # Identify ALL over-cap groups in this pass
    over_groups: dict[str, tuple[list[Any], float]] = {}
    for group, members in group_members.items():
        group_total = sum(w[m] for m in members)
        if group_total > group_cap + 1e-10:
            over_groups[group] = (members, group_total)

    if not over_groups:
        return False, pinned_ids

    # All members of newly capped groups + previously pinned ids
    all_capped_members: set[Any] = set(pinned_ids)
    excess_by_member: dict[Any, float] = {}

    for members, group_total in over_groups.values():
        excess = group_total - group_cap
        scale = group_cap / group_total
        all_capped_members.update(members)
        for m in members:
            pre_w = float(w[m])
            w[m] *= scale
            excess_by_member[m] = excess * (pre_w / group_total)

    # Redistribute each member's portion of excess to non-capped recipients
    for m, m_excess in excess_by_member.items():
        _redistribute(
            w,
            m_excess,
            m,
            cluster_assignment,
            exclude_ids=all_capped_members,
            per_name_cap=per_name_cap,
        )

    return True, all_capped_members


# ---------------------------------------------------------------------------
# Main allocator
# ---------------------------------------------------------------------------


@dataclass
class HrpAllocator:
    """HRP portfolio allocator.

    Attributes
    ----------
    corr_window_days : int
        Informational — caller supplies a returns panel of this length.
    single_name_cap : float
        Maximum weight for any single instrument. Default 5%.
    sector_cap : float
        Maximum aggregate weight for any single sector. Default 25%.
    issuer_group_cap : float
        Maximum aggregate weight for any issuer group. Default 5%.
    weight_floor : float
        Names with weight below this threshold after capping are dropped.
        Default 0.5%.
    """

    corr_window_days: int = 252
    single_name_cap: float = 0.05
    sector_cap: float = 0.25
    issuer_group_cap: float = 0.05
    weight_floor: float = 0.005

    def allocate(
        self,
        returns_panel: pd.DataFrame,
        sector_map: dict[uuid.UUID, str],
        issuer_group_map: dict[uuid.UUID, str],
    ) -> HrpResult:
        """Run HRP allocation.

        Parameters
        ----------
        returns_panel : pd.DataFrame
            Daily returns — cols are instrument UUIDs, rows are dates.
            Minimum 20 rows; 252 rows recommended.
        sector_map : dict
            Maps instrument_id → sector name.
        issuer_group_map : dict
            Maps instrument_id → issuer/promoter group name.

        Returns
        -------
        HrpResult
            Normalized weights + cluster assignments + binding cap labels +
            list of instruments dropped below the weight floor.
        """
        ids = list(returns_panel.columns)
        n = len(ids)

        log.debug("hrp_allocate_start", n_instruments=n, rows=len(returns_panel))

        # --- Single instrument edge case ---
        if n == 1:
            w = pd.Series({ids[0]: 1.0})
            return HrpResult(
                weights=w,
                cluster_assignment={ids[0]: "C1"},
                caps_binding=[],
                dropped_below_floor=[],
            )

        # -----------------------------------------------------------------------
        # Step 1: Correlation → distance matrix
        # -----------------------------------------------------------------------
        corr = returns_panel.corr()
        corr = corr.fillna(0.0)
        corr_arr = corr.values.copy()
        np.fill_diagonal(corr_arr, 1.0)
        corr = pd.DataFrame(corr_arr, index=corr.index, columns=corr.columns)
        dist: np.ndarray = np.sqrt(np.clip(0.5 * (1.0 - corr.values), 0.0, 1.0))
        condensed = ssd.squareform(dist, checks=False)

        # -----------------------------------------------------------------------
        # Step 2: Hierarchical clustering (single linkage)
        # -----------------------------------------------------------------------
        linkage_matrix = sch.linkage(condensed, method="single")

        leaf_order = _quasi_diagonalize(linkage_matrix, n)
        items_sorted = [ids[i] for i in leaf_order]

        n_clusters = max(2, min(n // 2, 8))
        cluster_assignment = _assign_clusters(linkage_matrix, ids, n_clusters)

        # -----------------------------------------------------------------------
        # Step 3: Recursive bisection
        # -----------------------------------------------------------------------
        cov = returns_panel.cov()
        weights = _recursive_bisection(cov, items_sorted)
        weights = weights.reindex(ids).fillna(0.0)

        total = weights.sum()
        if total > 0:
            weights = weights / total

        # -----------------------------------------------------------------------
        # Cap stack — sum-preserving clamp passes, outer loop for convergence
        # -----------------------------------------------------------------------
        caps_triggered: set[str] = set()
        # Per-name cap for redistribution eligibility purposes
        effective_per_name = self.single_name_cap

        for _outer in range(50):
            changed = False

            # a. Single-name cap
            if _clamp_name(weights, self.single_name_cap, cluster_assignment):
                caps_triggered.add("name")
                changed = True

            # b. Sector cap — inner loop with pinned_ids to prevent ping-pong
            # Each pass pins the members of capped sectors so excess can't flow
            # back to previously-capped sectors.
            pinned_sectors: set[Any] = set()
            for _inner_s in range(50):
                sector_bound, pinned_sectors = _clamp_group(
                    weights,
                    sector_map,
                    self.sector_cap,
                    cluster_assignment,
                    effective_per_name,
                    pinned_ids=pinned_sectors,
                )
                if sector_bound:
                    caps_triggered.add("sector")
                    changed = True
                else:
                    break  # sector cap fully satisfied

            # c. Issuer-group cap — same inner loop with pinned_ids
            pinned_groups: set[Any] = set()
            for _inner_g in range(50):
                group_bound, pinned_groups = _clamp_group(
                    weights,
                    issuer_group_map,
                    self.issuer_group_cap,
                    cluster_assignment,
                    effective_per_name,
                    pinned_ids=pinned_groups,
                )
                if group_bound:
                    caps_triggered.add("group")
                    changed = True
                else:
                    break  # group cap fully satisfied

            if not changed:
                break  # all caps satisfied

        caps_binding: list[str] = sorted(
            caps_triggered, key=lambda x: ["name", "sector", "group"].index(x)
        )

        # Final normalization: correct floating-point drift accumulated across iterations
        # (sum should be ~1.0 already; this is a guard against accumulated rounding)
        final_sum = weights.sum()
        if final_sum > 0:
            weights = weights / final_sum

        # -----------------------------------------------------------------------
        # d. Weight floor — drop names below threshold, re-normalize
        # -----------------------------------------------------------------------
        dropped_below_floor: list[uuid.UUID] = []
        below_mask = weights < self.weight_floor - 1e-12
        if below_mask.any():
            dropped_below_floor = list(weights[below_mask].index)
            weights = weights[~below_mask]
            floor_sum = weights.sum()
            if floor_sum > 0:
                weights = weights / floor_sum

        log.debug(
            "hrp_allocate_done",
            n_surviving=len(weights),
            n_dropped=len(dropped_below_floor),
            caps_binding=caps_binding,
            weight_sum=float(weights.sum()),
        )

        # Restrict cluster_assignment to surviving instruments
        surviving_set = set(weights.index)
        cluster_assignment = {k: v for k, v in cluster_assignment.items() if k in surviving_set}

        return HrpResult(
            weights=weights,
            cluster_assignment=cluster_assignment,
            caps_binding=caps_binding,
            dropped_below_floor=dropped_below_floor,
        )
