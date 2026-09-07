# Global Atlas — the FM's setup, in order

One sitting, roughly an hour. `runbook.md` is the reference for every command and what to do when
something fails; this file is only the ORDER, so nothing is done out of sequence and nothing is
hunted for. Each step says how long it takes and how you know it worked.

**The point of this order:** steps 1–6 get you a deployed board you can log into, showing real
instruments, sectors, index membership and liquidity, **without a price feed**. Prices are step 7
and they gate everything numeric. Do 1–6 now; the board is worth looking at while the price work
lands, and design feedback is cheapest before the scored surfaces are built on top of it.

---

## 1. The Alpaca keys — 2 minutes, do it first

Paper account, email signup, no card, no KYC. It unblocks the three chunks that are otherwise
idle: prices, technicals, and every price-derived surface on the board.

`app.alpaca.markets` → **Home**, right-hand panel → **Generate New Key**. The secret is shown
**once**; regenerating invalidates the previous pair. Paste both as text — a screenshot cannot be
transcribed reliably (the first attempt misread five characters and every call returned 401).

```
ALPACA_API_KEY=<key>          # 20 characters, starts PK for a paper account
ALPACA_API_SECRET=<secret>    # 40 characters
GLOBAL_PRICE_PROVIDER=alpaca
```

into the laptop and box `.env`. **Nothing is bought.** The free plan already passed the gate that
decides the spine — `validate_global.py --check SIP`, run 2026-09-07, 8 of 8 checks green on real
bars (`data-sources.md` carries the numbers). The $30/month feed the earlier draft asked you to buy
is not needed and stays the contingency.

Only these three values are read. `GLOBAL_PRICE_PROVIDER` accepts `alpaca` or `stooq_bulk` and
nothing else — any other value stops `ingest_prices` rather than quietly ingesting an untested feed.

Done when: the three lines are in `.env`. The gate itself is step 7.

## 2. The other two keys — 1 minute

```
EDGAR_IDENTITY="Nimish Shah nimish.shah1989@gmail.com"   # SEC fair-access User-Agent
FRED_API_KEY=<India's key, same account>          # OPTIONAL — see below
```

`build_identity.py` refuses to run without the first. The second is OPTIONAL: without it
`ingest_macro.py` reads FRED's keyless CSV export instead of the JSON API — the same observations
from the same publisher — so nothing is blocked on it. Supply it when convenient; the JSON API
carries revision vintages the export does not.

Done when: `grep -c EDGAR_IDENTITY .env` prints 1.

## 3. Apply the schema — 5 minutes

`runbook.md` §2. Read the seed rows before writing them; they are the methodology's starting
values and every one of them is editable later from the admin panel.

Done when: `python -m atlas.db` prints `atlas_global_exists True`, and the seed script reports the
threshold rows inserted.

## 4. The board's database role — 5 minutes

`runbook.md` §3, run as the project owner. The board reads through this role and can never reach
the India schema.

Done when: the verification line in §3 fails with permission denied. A success there is a bug.

## 5. Vercel + Supabase Auth — 20 minutes

`runbook.md` §4. Vercel project rooted at `frontend-global`, region `bom1`; Supabase magic link
enabled with the callback allowlisted; your row inserted into `app_user` with role `fm`.

Done when: the preview URL redirects you to `/login`, a magic link signs you in, and `/health`
renders (empty tables are correct — nothing has run yet).

## 6. Fill the board with facts — 15 minutes, no price feed needed

```
uv run python scripts/global_market/build_identity.py --report identity.csv
uv run python scripts/global_market/seed_benchmarks.py
uv run python scripts/global_market/ingest_index_membership.py --history --eod <last session>
```

This is the whole instrument universe, the S&P 500 with its history back to 2016, sectors, and the
benchmark ETFs. Roughly thirteen thousand instruments, of which about five and a half thousand are
ETFs.

Done when: the board's ETF and stock lists render real rows, and a detail page shows identity,
aliases and index membership. Price columns are honestly empty at this point — that is the design,
not a fault.

## 7. Prices — nothing for you to do until `ingest_prices` lands (P1-B)

The gate that stood in front of this is done: `--check SIP` PASSED on 2026-09-07 with your keys,
so the feed question is closed and the backfill is mine to run. Re-run it yourself only if the
account changes (`runbook.md` §5 has the command).

One limit worth knowing, because it shapes what the board can show: **Alpaca's history stops at
2016-01-04** — for every symbol, including ones listed in 1980. That is exactly the ten years the
plan asks for and not a day more. Anything older comes from the Stooq archive you downloaded, which
reaches 1970 for the oldest names. So Stooq is not the emergency fallback any more; it is the
permanent deep-history source, and it stays the nightly cross-check on top of that.

The backfill to 2016 runs overnight. Only after prices exist do technicals, returns, relative
strength, the charts and the return calculator have anything to compute.

## 8. Cron — last

`runbook.md` §6, and only after step 7: the nightly gates anchor on the SPY session calendar, so
installing the cron before prices exist just produces failing runs every night.

---

## What is decided and what is still open

| | |
|---|---|
| Liquidity floor | $1,000,000 median daily value, set 2026-09-06 from the real distribution in `reports/adv_usd_2026-09-03.md` |
| Stock universe | S&P 500 members only |
| Leveraged and inverse ETFs | excluded from the universe |
| Price spine | **Alpaca**, free plan, decided 2026-09-07 by the SIP gate (8/8 on real bars). Stooq is the permanent pre-2016 source and the nightly cross-check |
| Still open | Alpaca's corporate-actions tier and its display terms (before Phase 3, not now), the Phase 2 classification thresholds, the 150-ETF labelling set |
