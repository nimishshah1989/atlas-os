"""Household roll-up + succession-risk flags: real families (not the ledger's
family_group RM-territory code) rolled up from two independent signals —
shared surname within the ledger's own family_group folder, and joint-holder
containment — via union-find, so a family scattered across folio types still
shows up as one household in the book view and client-page header.

wealth.clients.family_group is NOT a family id — it's the ledger source
FOLDER name (parse_jhaveri.py: `res["family_group"] = path.parent.name`; see
docs/wealth-recommendation-framework.md: "191931 alone is 158 clients / ₹336cr
— an RM territory, not a family"). 175/234 clients share that one folder. So
family_group only narrows a surname match to "same batch of ledgers" — it
does NOT itself define a household; the surname match is what does.

Two independent edge types feed one union-find over client_id:

  1. surname match: normalized surname (last significant name token, see
     _surname() below) equal AND same family_group. Restricting to
     family_group is the brief's explicit guardrail — it keeps a common
     surname (Shah, Patel) from merging clients that only coincidentally
     share it across unrelated ledger batches.

     SIZE GATE (_SURNAME_CLUSTER_MAX): this edge is applied unconditionally
     only when the (family_group, surname) bucket has <= 8 members. A real
     nuclear/extended family sharing one surname inside one ledger batch
     tops out at 7 in this data (members-distribution counts: 1:76 2:16 3:7
     4:6 5:1 6:2 7:1 households) — every cluster above that is one of the
     two RM-territory false positives inside the 191931 mega-batch (Shah 38,
     Patel 27: unrelated clients who only share a surname + the RM's ledger
     folder, not a family). 8 sits exactly between the largest genuine
     cluster (7) and the smallest mega-cluster (27), so it separates the two
     populations cleanly on this data without needing to guess a family
     count. Clusters above the gate get NO surname edge at all — members
     still merge into a household if (and only if) a joint_holders edge
     (type 2 below) independently links them, which is how the Amin
     4-member household (well under the gate) is unaffected, while the two
     mega-clusters shrink to just their genuine joint-holder-linked pairs
     plus singletons. Kept as a documented module constant, not an
     atlas_thresholds row: it's a structural shape of this normalization
     heuristic (a batch-size crossover point empirically read off this one
     ledger import), not a business/methodology knob anyone would tune from
     /admin/thresholds — unlike e.g. the composite lens weights.
  2. joint_holders containment: wealth.client_profile_ext.joint_holders is a
     '/'-separated list of the names on that folio, primary holder first
     (verified against every sampled record: segment 0 is always that row's
     own client). If a client's own normalized name shares >=2 significant
     tokens with one of another client's joint_holders segments AFTER the
     first (i.e. an actual co-holder, not the primary/self entry repeated),
     the two are unioned — this is how a primary holder and a joint holder
     who also happens to hold their own folio land in the same household,
     even across family_group folders. Segment 0 is deliberately excluded:
     an earlier version matched it too and, on a single-holder folio (no
     '/' at all — segment 0 is the client's own full name with nothing
     else), it token-matched siblings across *different* family_group
     folders purely because they share a father's name + surname (e.g.
     "Yash Bhadresh Jhaveri" / "Jeet Bhadresh Jhaveri") — a real-looking but
     unverifiable relationship the ledger text doesn't actually assert
     anywhere; only a genuine multi-name folio counts as evidence here.

Known blind spots (both false-negative, not false-positive — a missed link,
not a wrong one): (a) surname-FIRST ALL-CAPS ledger entries ("PARIKH SANJAY
H") take the wrong token as "surname" under the last-token rule — this
under-links rather than over-merges, since the bogus token is unlikely to
coincide with anyone else's real surname; (b) a joint holder who is named on
two folios but has no client record of their own doesn't bridge those two
folios (edge type 2 only fires between two clients that both exist in
wealth.clients).

succession_flag (one value per household, stamped on every member row):
  transmission_seen           any member has a transmission_in/transmission_out
                               row in wealth.transactions — an inheritance/
                               transmission event already happened somewhere
                               in this household.
  single_holder_concentrated  household has exactly one member AND that
                               member's wealth.client_overlap.top10_share is
                               at/above the 75th percentile of all clients
                               that have one — an unusually concentrated
                               book with no second holder on record. Chosen
                               over eff_bets (inverse-Herfindahl "effective
                               bet count") because top10_share reads directly
                               as "how much rides on this one account";
                               clients absent from client_overlap (no equity
                               look-through) can't be assessed -> "none".
  none                         neither condition holds.

Usage: .venv/bin/python scripts/wealth/build_household.py
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict

import pandas as pd
from engine_common import connect
from psycopg2.extras import execute_values

# Size gate for the surname+family_group edge — see module docstring.
_SURNAME_CLUSTER_MAX = 8

# Generic tokens dropped before taking the surname / matching joint-holder names.
_STRIP = {
    "HUF", "MINOR", "TRUST", "LTD", "LIMITED", "PVT", "PRIVATE", "CO",
    "COMPANY", "GRAT", "AND", "THE", "OF", "MR", "MRS", "DR", "SHRI", "SMT",
}


def _tokens(name: str) -> list[str]:
    n = re.sub(r"[().,\-/]", " ", (name or "").upper())
    return [t for t in n.split() if t and t not in _STRIP]


def _surname(name: str) -> str | None:
    """Last significant token, skipping trailing 1-2 char initials
    ("PARIKH SANJAY H" -> drops "H"). See module docstring for the known
    surname-first-format blind spot this doesn't fully solve."""
    toks = _tokens(name)
    while toks and len(toks[-1]) <= 2:
        toks.pop()
    return toks[-1] if toks else None


class _UnionFind:
    def __init__(self, ids):
        self.parent = {i: i for i in ids}

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


def compute_all(conn) -> list[dict]:
    clients = pd.read_sql(
        "select client_id, full_name, family_group from wealth.clients order by client_id", conn
    )
    profile = pd.read_sql(
        "select client_id, joint_holders from wealth.client_profile_ext order by client_id", conn
    )
    mv = pd.read_sql(
        "select client_id, coalesce(sum(market_value),0)::float mv from wealth.ledger_blocks group by 1",
        conn,
    )
    txns = pd.read_sql(
        "select distinct client_id from wealth.transactions "
        "where txn_type in ('transmission_in','transmission_out')",
        conn,
    )
    overlap = pd.read_sql("select client_id, top10_share::float t10 from wealth.client_overlap", conn)

    uf = _UnionFind(clients.client_id.tolist())

    # ---- edge type 1: surname match within family_group, size-gated (see
    # module docstring _SURNAME_CLUSTER_MAX) — clusters above the gate rely
    # solely on edge type 2 (joint_holders) to merge any of their members ----
    clients["surname"] = clients.full_name.apply(_surname)
    for _, g in clients[clients.surname.notna()].groupby(["family_group", "surname"]):
        ids = g.client_id.tolist()
        if len(ids) > _SURNAME_CLUSTER_MAX:
            continue
        for cid in ids[1:]:
            uf.union(ids[0], cid)

    # ---- edge type 2: joint_holders containment (>=2 shared significant tokens,
    # co-holder segments only — segment 0 is the primary/self holder, skipped) ----
    name_tokens = {cid: frozenset(_tokens(nm)) for cid, nm in zip(clients.client_id, clients.full_name)}
    for row in profile.itertuples():
        if not row.joint_holders or "/" not in row.joint_holders:
            continue  # no '/' -> single-holder listing, no co-holder evidence
        for seg in row.joint_holders.split("/")[1:]:
            seg_tok = frozenset(t for t in _tokens(seg) if len(t) > 1)
            if len(seg_tok) < 2:
                continue
            for other_cid, other_tok in name_tokens.items():
                if other_cid != row.client_id and len(seg_tok & other_tok) >= 2:
                    uf.union(row.client_id, other_cid)

    # ---- group client_ids into households ----
    groups: dict[int, list[int]] = defaultdict(list)
    for cid in clients.client_id:
        groups[uf.find(cid)].append(cid)

    mv_by = dict(zip(mv.client_id, mv.mv))
    surname_by = dict(zip(clients.client_id, clients.surname))
    name_by = dict(zip(clients.client_id, clients.full_name))
    transmission_ids = set(txns.client_id)
    top10_by = dict(zip(overlap.client_id, overlap.t10))
    conc_floor = float(overlap.t10.quantile(0.75)) if len(overlap) else None

    rows: list[dict] = []
    for hh_id, (_root, members) in enumerate(sorted(groups.items()), start=1):
        members = sorted(members)
        hh_mv = round(sum(mv_by.get(c, 0.0) for c in members), 2)

        if any(c in transmission_ids for c in members):
            flag = "transmission_seen"
        elif len(members) == 1 and conc_floor is not None and top10_by.get(members[0], -1.0) >= conc_floor:
            flag = "single_holder_concentrated"
        else:
            flag = "none"

        if len(members) == 1:
            hname = name_by[members[0]]
        else:
            surnames = [surname_by[c] for c in members if surname_by.get(c)]
            common = max(set(surnames), key=surnames.count) if surnames else None
            hname = f"{common.title()} Family" if common else f"{name_by[members[0]]} Household"

        for cid in members:
            rows.append(dict(
                household_id=hh_id, client_id=int(cid), household_name=hname,
                members=len(members), household_mv=hh_mv, succession_flag=flag,
            ))
    return rows


def main() -> int:
    conn = connect()
    rows = compute_all(conn)

    cur = conn.cursor()
    cur.execute("drop table if exists wealth.households")
    cur.execute(
        """create table wealth.households (
             household_id bigint not null,
             client_id bigint not null references wealth.clients(client_id),
             household_name text,
             members int,
             household_mv numeric(18,2),
             succession_flag text,
             primary key (household_id, client_id)
           )"""
    )
    execute_values(
        cur,
        """insert into wealth.households
             (household_id, client_id, household_name, members, household_mv, succession_flag)
           values %s""",
        [(r["household_id"], r["client_id"], r["household_name"], r["members"],
          r["household_mv"], r["succession_flag"]) for r in rows],
        page_size=500,
    )
    cur.execute("revoke all on wealth.households from anon, authenticated")
    conn.commit()

    hh_df = pd.DataFrame(rows).drop_duplicates("household_id")
    n_households = len(hh_df)
    total_mv = float(hh_df.household_mv.astype(float).sum())
    biggest = hh_df.loc[hh_df.members.astype(float).idxmax()]

    print(f"households: {n_households} across {len(rows)} clients")
    print("members distribution:")
    print(hh_df.members.value_counts().sort_index().to_string())
    print("succession flag counts:")
    print(hh_df.succession_flag.value_counts().to_string())
    print(f"largest household: {biggest.household_name!r} ({biggest.members} members, "
          f"₹{float(biggest.household_mv) / 1e7:.2f} cr = "
          f"{float(biggest.household_mv) / total_mv:.1%} of total book)")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
