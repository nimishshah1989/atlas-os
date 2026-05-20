# Chunk T3.3 — Policy-Compliance Check: Approach

## Data scale
Pure function — no DB access. No table scan needed. Holdings are passed in as a
list; in production a portfolio has 15–50 holdings. O(n) is well within budget.

## Chosen approach
Pure Python, Decimal arithmetic throughout. A `Holding` frozen dataclass carries
the per-holding fields the checker needs; `ComplianceBreach` frozen dataclass
carries one breach record. `check_compliance` returns a plain list.

No SQL, no pandas, no external calls. This is a classification function on a
small list — there is no data-scale argument for anything other than simple
Python iteration.

## Wiki patterns checked
- `Decimal Not Float` — all weight/pct fields as Decimal; str-construction at
  boundary if needed.
- `PRD Golden Example Testing` — hand-computed golden values drive the tests;
  implementation must satisfy them, not the other way around.

## Existing code reused
- `Policy` dataclass from `atlas.intelligence.policy.policy` (imported directly).
- Frozen-dataclass pattern from `sizing.py` (`PositionSizeResult`) and
  `entry_filter.py` (`CandidateInstrument`).
- Test class structure from `test_sizing.py`.

## Holding input fields — chosen and rationale

```python
@dataclass(frozen=True)
class Holding:
    instrument_id: str        # identifier for breach messages
    weight_pct: Decimal       # current weight, whole-number percent
    sector: str               # for max_per_sector check
    is_small_cap: bool        # True = small-cap; cleaner than a string cap_tier
                              # because the compliance rule only needs a binary split
```

`is_small_cap: bool` chosen over `cap_tier: str` because:
- The max_small_cap rule only needs a binary: counts small-cap weight vs not.
- A bool is unambiguous; a cap_tier string ("small", "mid", "large") would
  require a mapping and introduce a new string-matching concern.
- The caller (Act step) already knows whether a stock is small-cap from the
  universe table's market_cap_tier column; mapping to bool at the call site is
  one expression.

## Six rules implemented

| Rule id         | Logic                                                          |
|-----------------|----------------------------------------------------------------|
| `max_per_stock` | holding.weight_pct > policy.max_per_stock_pct → 1 breach/holding |
| `max_per_sector`| sum(weight_pct) per sector > policy.max_per_sector_pct → 1 breach/sector |
| `max_small_cap` | sum(weight_pct where is_small_cap) > policy.max_small_cap_pct → 1 breach |
| `min_holdings`  | len(holdings) < policy.min_holdings → 1 breach               |
| `max_positions` | len(holdings) > policy.max_positions → 1 breach               |
| `cash_floor`    | (100 − sum(all weight_pct)) < policy.cash_floor_pct → 1 breach |

Cash floor: invested = sum of all weight_pct. cash = 100 − invested.
Breach when cash < cash_floor_pct.

## Edge cases
- Empty holdings list: min_holdings breach fires (0 < min_holdings), no
  per-stock or per-sector breaches. Cash = 100 (no breach on cash_floor unless
  cash_floor_pct > 100, which validate_policy already blocks).
- weights sum to exactly 100 − cash_floor_pct: NOT a breach (boundary is
  exclusive: cash STRICTLY LESS THAN floor).
- Two holdings in same sector, each under per-stock cap but sum over sector cap:
  sector breach fires, no per-stock breaches.
- NULL / None weight_pct: not possible with a frozen Decimal field — type
  enforced at construction time.

## Expected runtime
Trivially fast on any hardware. O(n) over holdings count. No concern.

## Files
- Create: `atlas/intelligence/policy/compliance.py` (≤250 LOC)
- Create: `tests/intelligence/policy/test_compliance.py` (≤800 LOC)
- Update: `atlas/intelligence/policy/__init__.py`
