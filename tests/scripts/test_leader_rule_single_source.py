"""The leader rule lives in ONE place — atlas_foundation.v_stock_leader.

Three tasks in a row on this branch hit the same failure: a rule copy-pasted across
files, every copy internally consistent, none of them agreeing, and no test able to
notice. For the leader flag that meant fund_rank_daily.breadth was computed on
(d_tech>=9)+(d_flow>=9)>=2 while the funds page displayed (d_composite>=10)>=1 — 73
leaders vs 25 on 2026-08-18 — and the DoD gate passed because the verifier had copied
the builder rather than production.

No data test can catch that: each copy is self-consistent. Only a structural check can.
This is that check, over the four call sites on the fund/ETF breadth path.

OUT OF SCOPE (pre-existing, and they agree with production today): stock_lens.ts
derives the flag twice and sector_lens.ts once — both need the composite decile itself
for display, so they compute it locally; build_sector_cards.py counts leaders in pandas
off its own ntile. Those are reported, not changed, by the task that wrote this file.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[2]

# Every consumer on the fund/ETF breadth path, and how each is allowed to reach the rule:
# by naming the view, or — for fund_lens.ts — by importing etf_lens.ts's SCORED_STOCKS CTE,
# which names it. Anything else means the file has grown its own copy again.
CONSUMERS = {
    "frontend/src/lib/queries/etf_lens.ts": "v_stock_leader",
    "frontend/src/lib/queries/fund_lens.ts": "SCORED_STOCKS",
    "scripts/foundation/build_fund_rank_history.py": "v_stock_leader",
    "scripts/foundation/verify_fund_rank.py": "v_stock_leader",
}

# A locally-derived leader flag: the current rule, or the retired 2-lens one.
LOCAL_RULE = re.compile(r"d_composite\s*>=\s*10|d_tech\s*>=\s*9|d_flow\s*>=\s*9")


@pytest.mark.parametrize(("rel", "source"), CONSUMERS.items())
def test_consumer_reads_the_leader_view_and_does_not_re_derive_it(rel: str, source: str) -> None:
    src = (REPO / rel).read_text()
    body = "\n".join(ln for ln in src.splitlines() if not _is_comment(ln))
    if "lead" not in body:
        pytest.fail(f"{rel} no longer uses the leader flag — drop it from CONSUMERS")
    assert source in body, f"{rel} no longer resolves the leader flag through {source}"
    local = LOCAL_RULE.findall(body)
    assert not local, f"{rel} re-derives the leader rule locally: {local}"


def _is_comment(line: str) -> bool:
    s = line.lstrip()
    return s.startswith("--") or s.startswith("//") or s.startswith("#")
