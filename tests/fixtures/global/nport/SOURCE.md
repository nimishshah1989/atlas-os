# SEC EDGAR Form N-PORT-P — real filings, dated snapshot

Four real `www.sec.gov/Archives` downloads of `primary_doc.xml`, fetched on **2026-09-09**
with a contact `User-Agent` (SEC fair access). They exist so
`tests/unit/global_market/test_nport.py` runs the parser against filings real registrants
made, offline and with no database (rule #0: never a fabricated fixture, never a `Mock()`
filing). **Refresh by re-fetching, never by editing.**

## What was changed

**Nothing.** Each file is the download, byte for byte, gzipped (`gzip -9 -n`, no timestamp)
because the four raw payloads come to 1.3 MB and the repository's cap is 1 MB per file.
`sha256` below is of the **uncompressed** payload, so
`gzip -dc <file>.gz | sha256sum` reproduces it; `test_the_fixtures_are_the_filings_as_served`
asserts exactly that.

| File | Fund | Accession | Filed | Period | sha256 (uncompressed) | Bytes |
|---|---|---|---|---|---|---|
| `ivv_primary_doc.xml.gz` | iShares Core S&P 500 ETF (IVV) · CIK 1100663 · S000004310 | `0002071691-26-019760` | 2026-08-25 | 2026-06-30 | `9924e5b86bf304d0c2d24679e15642b681de6605ed38ca8b1bb1db7aa5b3b7e9` | 512,667 |
| `tqqq_primary_doc.xml.gz` | ProShares UltraPro QQQ (TQQQ) · CIK 1174610 · S000024908 | `0002071691-26-017348` | 2026-07-28 | 2026-05-31 | `36ebaf3960bff364864f4efddaf9de06504a9d362eaef53155227ba2e11d121a` | 156,865 |
| `voo_primary_doc.xml.gz` | Vanguard 500 Index Fund (VOO) · CIK 36405 · S000002839 | `0000036405-26-000473` | 2026-08-28 | 2026-06-30 | `e5b36312ae54cd8e4d614b24a54310e0d1c7a948bc849ab3cb95fb239d8cca0f` | 500,233 |
| `ewj_primary_doc.xml.gz` | iShares MSCI Japan ETF (EWJ) · CIK 930667 · S000004249 | `0001004726-26-006437` | 2026-07-27 | 2026-05-31 | `77474976fd55df002052ebd4774a443077f3e777043438d2322d37f25027db6b` | 184,615 |

## Why these four funds

They are not samples; each one is the counter-example to a way the parser can be wrong.

* **IVV** — the ordinary path, and the file that pins the **units**. CBRE's `pctVal` is
  `0.061079735228` while `valUSD / netAssets` for the same row is `0.00061079…`: `pctVal` is a
  PERCENT, and a parser that stored it as a fraction would put the S&P 500 at 100× its weight.
  It also carries the two "OTHER" shapes — a Hologic CVR whose category is
  `<assetConditional assetCat="OTHER" desc="Right"/>` and an S&P 500 E-Mini future whose issuer
  is `<issuerConditional issuerCat="OTHER" desc="Future"/>` — and one money-market **CUSIP held
  on two lines**, which is why a holding key needs an occurrence suffix.
* **TQQQ** — the leverage case, and the one that kills a plausible shortcut. A three-times fund
  whose weights sum to **101.26%** of net assets against IVV's 100.12%: a swap's `pctVal` is its
  MARK, not its notional, so gearing is invisible in the weights. Its ten swaps' `notionalAmt`
  totals $107.5bn against $39.8bn of net assets — `derivative_notional_share` 2.70, against
  0.0016 for IVV. It is also the only fixture with `units` `PA` (principal amount) and an
  `RA` (repurchase agreement) category.
* **VOO** — the **multi-class** case. One `seriesClassInfo` block listing FOUR `classId`s: the
  filing's `netAssets` of $1.671tn is the whole Vanguard 500 Index Fund across its Investor,
  Admiral, Institutional and ETF classes, and N-PORT carries no class-level assets at all
  (there is no `classInfo` element in any of these four files). Calling that VOO's AUM would be
  a wrong number on a card, which is why `ingest_nport.py` fills `aum_usd` only where
  `series_class_count = 1`. Its twelve futures lines also file `invCountry` as the literal
  string `N/A`, which a `char(2)` column would happily store as `N/`.
* **EWJ** — the non-US path. **176 of its 182 holdings have no CUSIP** (Japanese equities have
  none) and every one of them has an ISIN, so ISIN is not a nicety; 180 rows carry
  `<currencyConditional curCd="JPY" exchangeRt="…"/>` in place of `<curCd>` while `valUSD`
  stays US dollars; and two rows file the ISIN itself as `N/A`. It is the file that proves
  "N/A" is a value the filers write, not an absence the parser can assume away.

## Refreshing

    UA="Firstname Lastname email@domain"
    curl -A "$UA" "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany\
    &CIK=S000004310&type=NPORT-P&count=4&output=atom"        # newest accession
    curl -A "$UA" -o - "https://www.sec.gov/Archives/edgar/data/1100663/\
    000207169126019760/primary_doc.xml" | gzip -9 -n > ivv_primary_doc.xml.gz

then update the row above (accession, filed, period, sha256 and byte count). These filings are
closed: a refresh moves to a LATER period rather than restating these, so the assertions that
name a period, a net-asset figure or a holding count move with the file — which is the point of
recording what each one was when it was fetched.
