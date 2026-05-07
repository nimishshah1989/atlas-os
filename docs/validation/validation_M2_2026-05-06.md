# Atlas-M2 Validation — 2026-05-06

## Tier 2 — Hand-computed metric checks

- Total checks: **455**
- Pass rate: **76.92%**
- Detail: [`m2_tier2_2026-05-06.csv`](./m2_tier2_2026-05-06.csv)

### Failures (105)

| instrument_id | date | metric | hand | prod | deviation |
|---|---|---|---|---|---|
| a50b07ad-9b7c-4f6d-ba77-db684a53b2e4 | 2021-11-08 | no_history | nan | nan | nan |
| a50b07ad-9b7c-4f6d-ba77-db684a53b2e4 | 2017-07-21 | no_history | nan | nan | nan |
| a50b07ad-9b7c-4f6d-ba77-db684a53b2e4 | 2021-10-26 | no_history | nan | nan | nan |
| a50b07ad-9b7c-4f6d-ba77-db684a53b2e4 | 2019-02-25 | no_history | nan | nan | nan |
| a50b07ad-9b7c-4f6d-ba77-db684a53b2e4 | 2022-10-19 | no_history | nan | nan | nan |
| 9ba7a2aa-19b9-43a7-b690-9d0c03f8952b | 2021-11-08 | ema_200_stock | 1305.731271319858 | 1309.5806 | 3.84932868014198 |
| 9ba7a2aa-19b9-43a7-b690-9d0c03f8952b | 2017-07-21 | ema_200_stock | 505.3197956162817 | 506.5204 | 1.2006043837183142 |
| 9ba7a2aa-19b9-43a7-b690-9d0c03f8952b | 2021-10-26 | ema_200_stock | 1285.3792164132649 | 1290.844 | 5.464783586735166 |
| 9ba7a2aa-19b9-43a7-b690-9d0c03f8952b | 2019-02-25 | ema_200_stock | 722.9497046486047 | 724.7488 | 1.7990953513952945 |
| 9ba7a2aa-19b9-43a7-b690-9d0c03f8952b | 2022-10-19 | ema_200_stock | 1745.0821605163633 | 1755.5806 | 10.49843948363673 |
| 47bf2e68-adf0-4546-8223-2ce930f25748 | 2021-11-08 | ema_200_stock | 323.2392557429106 | 332.3468 | 9.107544257089387 |
| 47bf2e68-adf0-4546-8223-2ce930f25748 | 2017-07-21 | no_history | nan | nan | nan |
| 47bf2e68-adf0-4546-8223-2ce930f25748 | 2021-10-26 | ema_200_stock | 326.2384802813943 | 335.75 | 9.511519718605712 |
| 47bf2e68-adf0-4546-8223-2ce930f25748 | 2019-02-25 | ema_200_stock | nan | nan | nan |
| 47bf2e68-adf0-4546-8223-2ce930f25748 | 2019-02-25 | ret_12m | nan | nan | nan |
| 47bf2e68-adf0-4546-8223-2ce930f25748 | 2019-02-25 | max_drawdown_252 | nan | nan | nan |
| 47bf2e68-adf0-4546-8223-2ce930f25748 | 2022-10-19 | ema_200_stock | 346.58455760330537 | 344.8319 | 1.7526576033053516 |
| 47bf2e68-adf0-4546-8223-2ce930f25748 | 2022-10-19 | max_drawdown_252 | 0.3616695804195801 | 0.405 | 0.04333041958041994 |
| fc14dbe6-fa71-4122-9add-5913faae0f51 | 2021-11-08 | ema_200_stock | 615.938486585036 | 620.505 | 4.5665134149639925 |
| fc14dbe6-fa71-4122-9add-5913faae0f51 | 2017-07-21 | ema_200_stock | 138.48054558080128 | 140.5366 | 2.0560544191987162 |

## Tier 3 — Hand-classified state checks

- Total checks: **120**
- Pass rate: **86.67%**
- Sample date: 2026-05-05
- Detail: [`m2_tier3_2026-05-06.csv`](./m2_tier3_2026-05-06.csv)

### Failures (16)

| instrument_id | state_type | hand | prod |
|---|---|---|---|
| d4d520d8-3615-4611-99ea-12b200f29af6 | momentum_state | Flat | Deteriorating |
| 7d784808-88c8-48c6-a6c2-b7ed530fb423 | rs_state | Consolidating | INSUFFICIENT_HISTORY |
| 7d784808-88c8-48c6-a6c2-b7ed530fb423 | momentum_state | Flat | INSUFFICIENT_HISTORY |
| 7d784808-88c8-48c6-a6c2-b7ed530fb423 | risk_state | High | INSUFFICIENT_HISTORY |
| 7d784808-88c8-48c6-a6c2-b7ed530fb423 | volume_state | Neutral | INSUFFICIENT_HISTORY |
| 623b83a8-e8b7-4303-ae2b-23bb0127e360 | rs_state | Weak | Average |
| 81af87f6-cc59-4d56-becb-2a4d43934c09 | rs_state | Weak | Average |
| faaf4cc8-9c5c-40a1-a1d5-c8fa45e6ed9a | rs_state | Laggard | Average |
| 3fccb8be-e130-4af0-aa82-05546e735804 | rs_state | Weak | Average |
| 3fccb8be-e130-4af0-aa82-05546e735804 | momentum_state | Flat | Deteriorating |
| 27e9e489-eff1-4689-8420-ec128146ae71 | rs_state | Weak | Average |
| 6c1eaa71-5942-4143-969a-327bc7f585a4 | rs_state | Weak | Average |
| 435937af-424f-491a-b801-5d6387770f3d | rs_state | Average | ILLIQUID |
| 435937af-424f-491a-b801-5d6387770f3d | momentum_state | Collapsing | ILLIQUID |
| 435937af-424f-491a-b801-5d6387770f3d | risk_state | Below Trend | ILLIQUID |
| 435937af-424f-491a-b801-5d6387770f3d | volume_state | Neutral | ILLIQUID |

## Verdict: **FAIL**
