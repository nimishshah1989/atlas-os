# Atlas v6 /v1 API Surface

> Read-only endpoints under the `/v1` prefix. All are JWT-auth-exempt
> (the prefix is in `atlas.api.auth._EXEMPT_PREFIXES`) and serve the
> v6 frontend directly. Mutation endpoints continue to live under
> `/api/*` with JWT enforcement.

All endpoints share the response envelope:

```json
{ "data": ..., "meta": { "data_as_of": "YYYY-MM-DD", "fetched_at": "ISO-8601", ... } }
```

Degraded responses (table empty / table not yet provisioned) return 200
with `meta.degraded=true` and an empty `data` payload — the frontend
contract is unbroken.

Errors:

* `503 database unavailable` — `OperationalError` from `get_engine()`
* `400 invalid cursor` — `/v1/screen.stocks` failed to decode the cursor
* `404 not found` — `/v1/instrument/{iid}` for an unknown instrument

---

## GET /v1/screen.stocks

Paginated screen of stocks with the per-tenure conviction tape attached.

### Query parameters

| name | type | default | notes |
|---|---|---|---|
| `cap_tier` | `string` | `null` | One of `Large` / `Mid` / `Small` |
| `sector` | `string` | `null` | Sector name (e.g. `Energy`) |
| `cursor` | `string` | `null` | Base64-encoded cursor from `meta.next_cursor` |
| `page_size` | `int` | `50` | 1..200 |

### Example response (truncated)

```json
{
  "data": [
    {
      "instrument_id": "uuid",
      "symbol": "RELIANCE",
      "company_name": "Reliance Industries",
      "sector": "Energy",
      "cap_tier": "Large",
      "conviction": [
        {
          "tenure": "3m",
          "verdict": "POSITIVE",
          "eli5": "...",
          "ic": 0.10,
          "friction_adjusted_excess": 0.05,
          "conflict": false
        }
      ]
    }
  ],
  "meta": {
    "data_as_of": "2026-05-22",
    "fetched_at": "2026-05-24T18:42:07Z",
    "source": "atlas_conviction_daily",
    "next_cursor": "eyJpaWQiOiJ1dWlkIiwiZCI6IjIwMjYtMDUtMjIifQ==",
    "page_size": 50
  }
}
```

---

## GET /v1/screen.etfs

ETF universe view. Returns the full `atlas_universe_etfs` rows with
empty conviction lists (ETFs do not yet have scorecard rows). NEGATIVE
rows are stripped upstream when the scorecard is wired.

---

## GET /v1/screen.funds

Mutual-fund screen. Returns `atlas_mf_master` rows with AUM but the v6
fund-conviction score is null and `meta.degraded=true` — the v6 MF
conviction model is not yet wired. Endpoint exists so the frontend
contract is satisfied day-1.

---

## GET /v1/screen.sectors

Sector view backed by `atlas_sector_states_daily` (SP02 MV when present).
Each row carries `sector`, `strength_rank`, `breadth_pos`, and a
(currently empty) `top_constituents` list reserved for a future join
back to stocks.

---

## GET /v1/market.regime

Current regime + 252-day history + cells preferred under the current
state. The `preferred_cells` list is derived from
`atlas_cell_definitions.confidence_by_regime[<current_state>]` sorted
by confidence DESC.

### Example response

```json
{
  "data": {
    "current": {
      "date": "2026-05-22",
      "state": "Risk-On",
      "smallcap_rs_z": "0.50",
      "breadth_pct_above_200dma": "0.65",
      "vix_percentile": "0.30"
    },
    "history": [ {"date": "...", "state": "...", ... }, ... ],
    "preferred_cells": [
      {"cell_id": "uuid", "cap_tier": "Large", "action": "POSITIVE",
       "tenure": "3m", "confidence": "0.70"}
    ]
  },
  "meta": {
    "data_as_of": "2026-05-22",
    "fetched_at": "...",
    "history_points": 252
  }
}
```

---

## GET /v1/cell.definitions

Every active cell + its top-K candidate runner-ups from
`atlas_cell_rule_candidates`. Default `top_k=5`, max 20.

### Query parameters

| name | type | default | notes |
|---|---|---|---|
| `top_k` | `int` | `5` | 1..20 |

### Example response

```json
{
  "data": [
    {
      "cell_id": "uuid",
      "cap_tier": "Large",
      "action": "POSITIVE",
      "tenure": "3m",
      "methodology_lock_ref": "DEEP_SEARCH_V2_2026-05-24",
      "confidence_unconditional": "0.55",
      "friction_adjusted_excess": "0.10",
      "drift_status": "healthy",
      "rule_dsl": { "rule_type": "accumulate", "eligibility": [...], "entry": [...] },
      "candidates": [
        {
          "candidate_id": "uuid",
          "rank": 1,
          "archetype": "quality_momentum",
          "ic": "0.12",
          "friction_adjusted_excess": "0.10",
          "bh_q_value": "0.05",
          "eli5": "Consistent Large-cap leaders ..."
        }
      ]
    }
  ],
  "meta": { "fetched_at": "...", "n_cells": 21, "top_k": 5 }
}
```

---

## GET /v1/instrument/{iid}

Per-instrument deep view.

### Response payload

```json
{
  "data": {
    "instrument": {
      "instrument_id": "uuid",
      "symbol": "RELIANCE",
      "company_name": "...",
      "sector": "...",
      "cap_tier": "Large"
    },
    "conviction": [ { /* one TenureConviction row per tenure */ } ],
    "history": [ { "snapshot_date": "...", "tenure": "...", "verdict": "..." } ],
    "similar": [ { "instrument_id": "...", "symbol": "...", "last_fired": "..." } ]
  },
  "meta": {
    "data_as_of": "2026-05-22",
    "fetched_at": "...",
    "history_days": 30
  }
}
```

The `similar` list contains other instruments that fired the same
`best_rule_id` as this instrument's latest conviction row within the
last 30 days. Limited to 20.

---

## Implementation files

| Endpoint | Source |
|---|---|
| `/v1/screen.*` | `atlas/api/screen.py` |
| `/v1/market.regime` | `atlas/api/market.py` |
| `/v1/cell.definitions` | `atlas/api/cell_defs.py` |
| `/v1/instrument/{iid}` | `atlas/api/instrument.py` |

Tests: `tests/api/test_v6_endpoints.py` (13 unit tests, all mocked).
