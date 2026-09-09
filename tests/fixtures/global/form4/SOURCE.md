# SEC Form 4 ownership documents — provenance

Seven verbatim, unmodified downloads of raw Form 4 XML from `https://www.sec.gov/Archives/edgar/`,
fetched **2026-09-09** with the contact `User-Agent` the SEC's fair-access policy requires. Public
insider-transaction filings: no key, no position of ours, no client data.

| File | sha256 |
|---|---|
| `AAPL_0001140361-26-025622_exercise_withholding.xml` | `cc32376a3c8c83225ff570d3f79edbe5f101620f066dfc76ad0e65fa4a64a0e6` |
| `AAPL_0001140361-26-035362_award.xml` | `0cb08845a04b8958ea4eb7e9ea7dff2014f9436c3df8a8b53a833c0870a65c1d` |
| `AAPL_0001140361-26-035636_sale_10b51.xml` | `fcd091e16f995a813d107e5da4d78eaa41eb64a16a4f884cef359502642da7c1` |
| `JPM_0001225208-26-006542_no_transactions.xml` | `453be612a966c9f744c7ff6546d3368bf3b9f9ecbd681bab865114cad6ffd525` |
| `JPM_0001225208-26-006750_gift.xml` | `d3050d4ada3d710fc5c40512fb77ce9bd7b82b194f4177aea914cd45c6a255cc` |
| `JPM_0001225208-26-007064_sale_10b51.xml` | `7fe1ad18f500bc498b16b381bbd8ae150805accd99c91f9c32807a869affd985` |
| `VZ_0001760581-26-000050_sale.xml` | `e641dfe194cc9ff471789048358f1f4f7482fd182482a7bceda2de2deafd409e` |

Each was chosen because it is the *only* honest witness to one thing the parser or the lens can get
wrong.

## The census that shaped the lens

The 18 most recent Form 4s from Apple, JPMorgan and Verizon (six each) in the twelve months to
2026-09-09, counted **by the parser**, not by grepping the text:

| Table | Code | What it is | Count |
|---|---|---|---|
| non-derivative | `S` | Open-market sale | 6 — **every one under a Rule 10b5-1 plan** |
| non-derivative | `A` | Grant or award | 2 |
| non-derivative | `G` | Gift | 2 |
| non-derivative | `M` | Option exercise | 1 |
| non-derivative | `F` | Shares withheld for the tax on a vest | 1 |
| non-derivative | **`P`** | **Open-market purchase** | **0** |
| derivative | `A` | RSU / option grant | 6 |
| derivative | `M` | Exercise | 1 |

Seven of the eighteen filings carry no non-derivative transaction at all.

**Two findings, and both bear on what the flow lens can be.**

1. **Not one open-market purchase.** `plan.md` §B specs the lens as "Form 4 net open-market buying
   over 90 days as a percent of market cap". On this evidence that sub-score is absent for most
   S&P 500 names most of the time. A code-`P` is a *strong* signal precisely because it is rare —
   nobody buys their own stock by accident — but a lens built on it is silent far more often than
   it speaks.
2. **Not one discretionary sale either.** All six sales carry `aff10b5One`. The insider chose to
   sell months earlier, when they were free to trade, and the plan chose the date. So the *other*
   half of the signal is mechanical too.

Taken together: for large-cap US issuers, Form 4 carries very little discretionary information.
That is a property to plan around — and an argument for putting short interest (FINRA, twice
monthly, every name) and 13F holder counts ahead of Form 4 in the flow lens, rather than after it
as the plan currently orders them.

**A caveat on this census, stated because it is the honest bound.** Eighteen filings from three
healthy megacaps is not the S&P 500. Distressed and small-cap issuers are exactly where insider
buying happens, and none is represented here. What is safe to conclude is that the lens will be
sparse for names like these; the index-wide rate is a measurement still to be made.

**And a correction, recorded because it nearly became a wrong number in a design document.** The
first version of this census was computed with `grep 'aff10b5One>true'`, which silently missed
JPMorgan's and Verizon's `<aff10b5One>1</aff10b5One>` and reported "4 of 6 sales under a plan"
instead of six of six. It also counted derivative-table grants as non-derivative ones. The same
two-spellings trap the parser exists to handle caught the person writing about it.

## The four traps these files pin

1. **`aff10b5One`.** Apple's 2026-09-03 sale carries it, with a footnote naming a plan adopted on
   5 May. The insider chose to sell in May; the calendar chose September. Reading it as a fresh
   bearish decision is exactly wrong, and the flag is the only machine-readable way to know. There
   is **no discretionary sale in this fixture set** — every one of the six is a plan sale, which is
   itself the finding above.
2. **Two encodings of one boolean.** Apple writes `<isOfficer>true</isOfficer>`; JPMorgan writes
   `<isOfficer>1</isOfficer>`. A parser accepting only `"true"` reads every JPMorgan officer as not
   an officer — no error, no missing row, just a relationship silently lost.
3. **An empty filing is a real filing.** JPMorgan's 2026-07-08 document has `<nonDerivativeTable>`
   and `<derivativeTable>` both empty. It must parse to zero transactions, not raise.
4. **The document URL in the index is not the XML.** `primaryDocument` is
   `xslF345X06/form4.xml`, which EDGAR serves as an HTML *rendering* — 15,625 bytes for Apple's
   filing against 3,153 for the raw XML at the same name with the prefix stripped. Both return
   HTTP 200, so fetching the wrong one fails as a parse error far from its cause.
