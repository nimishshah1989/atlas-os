# Wealth Capability Atlas — everything client-level transaction data can power

**Date:** 2026-07-23 · research sweep for the capability-demo spec
(`docs/superpowers/specs/2026-07-23-wealth-capability-demo-design.md`).
Scope: the current book only (219 clients / 210,634 txns / ₹439 cr) treated as the
entire universe. Question answered: *are we comprehensive, and what does the world
know that we haven't built yet?*

## Verdict in one paragraph

The engines already built (exact benchmark, FIFO tax lots, behaviour fingerprints,
advice ledger, counterfactuals, survival-honest churn) cover the analytical core of
what the academic literature and the global platforms do with transaction data — in
some places (per-client exact flow replay; advice self-scoring) we are ahead of
commercial practice. The sweep surfaced **four genuinely missing capabilities** that
belong in the build (§C), a **value-quantification framing** that turns the whole
thing into the regular-vs-direct answer (§B1), and hard **compliance rails** the
recommendation engine must respect (§B10).

## A. Coverage check — what we built vs the canon

| Canon capability | Precedent | Our status |
|---|---|---|
| Investor-vs-fund return gap | Morningstar Mind the Gap (~1.1–1.2pp/yr US) | ✅ built, per client×fund, Hayley caveat encoded |
| Disposition effect measurement | Odean PGR/PLR; Barber-Odean survey ("remarkably consistent") | ✅ built on avg-cost positions |
| Under-diversification / welfare cost | Calvet-Campbell-Sodini (Swedish registry) | ✅ effective-N + overlap (in spec) |
| Personal benchmark / alpha | SPIVA-style + robo replays | ✅ exact ledger-flow replay (stronger than industry point-to-point) |
| Tax-aware lot accounting | US robo tax-loss harvesting (0.3–1.5%/yr quantified) | ✅ lots + grandfathering; harvest *optimizer* missing (§C2) |
| Churn/attrition modelling | Survival analysis, BTYD CLV | ✅ at honest levels (SIP-stream, holding); client-level blocked by survivorship — stated |
| Panic-selling prediction | MIT "When Do Investors Freak Out?" (ML on 600k+ accounts) | ✅ profile built; predictive *score + trigger* is the PREDICT layer of the spec |
| Advice self-scoring | (rare in industry — advisors don't audit themselves) | ✅ built (33k switches scored) — differentiator |
| AI narration of client portfolios | Aladdin Wealth AI commentary (Morgan Stanley, Oct 2025); Morningstar AI assistant (meeting briefs) | ✅ = our audit-pack narration layer; pattern validated by the two biggest platforms |

## B. What the research adds

### B1. The value-quantification layer — the regular-vs-direct answer ⭐
The industry's two canonical frameworks quantify advisor value: **Vanguard Advisor's
Alpha** — up to ~3%/yr potential, of which **behavioural coaching alone is 150–200bp**,
delivered "intermittently, during duress or euphoria" (the emotional-circuit-breaker
role); **Morningstar Gamma** — +1.59%/yr certainty-equivalent from five planning
decisions (withdrawal sequencing largest). Both are *projected* averages. **We can do
what neither can: compute the realized version per client from their own ledger** —
"in 2020 you didn't sell (we called you): that decision is worth ₹X today; harvesting
saved ₹Y; the fee swap saves ₹Z/yr" — an annual, auditable **Value Statement** in
rupees. That is the strongest possible answer to "why not direct plans?" and nobody
in the Indian market produces it. → joins the build (§C1).

### B2. Tax alpha, India-specific mechanics
Quantified at 0.3–1.5%/yr in practice. India specifics the engine must encode:
**gain-harvesting** inside the ₹1.25L LTCG exemption (resets every 1 April, use-it-or-
lose-it; sell-and-rebuy stepped-up basis; no wash-sale rule in India — clean re-entry);
**sequencing subtlety** — exemption applies before loss set-off, so harvesting losses
when gains are already under ₹1.25L wastes them (carry-forward instead, 8 years,
requires on-time ITR — a flag worth surfacing per client); Jan–Mar is the execution
window; grandfathering per lot (built). → harvest optimizer joins the build (§C2).

### B3. Panic prevention — evidence-backed playbook
MIT/Lo et al. show panic selling is *predictable* from history + demographics.
Intervention evidence: involvement/ownership nudges reduce panic selling (IKEA-effect
experiment); message *framing* changes sell behaviour; the 13M-person PNAS nudge RCT
says **one action per message**; retail-bank field work says effects are
**heterogeneous — personalise by client type** (= our personas). Direct large-scale
panic-message RCTs are rare → running our call-list interventions with a discipline
(who got called, who didn't, what happened) is both the uplift-training data AND a
publishable differentiator. → freak-out score + scripted one-action nudges (§C3).

### B4. Life-event inference
Peer-reviewed precedent (Decision Support Systems: 60M transactions → predicting
moves, childbirth, relationship changes) and US bank patents (retirement = paycheck
disappearance). Our ledger equivalents: SWP starts (income need), education-season
redemptions, **transmission events** (death — the single highest-churn moment; we
parse these), folio consolidations (household reorganisation), dormancy onsets.
→ event-detector rules now; ML later when AA data arrives.

### B5. Goals-based layer
Goals-based planning shows measurable utility gains (~15% utility-adjusted wealth,
FPA); glide-path research (Amundi 2026) says personalisation inputs beyond age are
the frontier — **our behavioural profile is exactly that input**. Vanguard's coaching
anchor is the IPS. Build later: infer implicit goals from flow shapes → propose a
one-page IPS per client → the IPS becomes the anchor the coaching refers back to.

### B6. Next-best-action discipline
BCG: NBA programs run propensity→uplift→bandit layers, and **20–40% of NBA actions
deliver nothing incremental** — uplift-first thinking is what separates working
programs. Our advice-ledger outcome loop is the uplift training set; start collecting
treatment/control discipline from day one of RM usage (even informal holdouts).

### B7. Household/family layer
We already hold family_group, joint holders, transmission records. Build: household
roll-up (true family exposure/overlap), succession-risk radar (single-holder aging
books, no joint/nominee activity), inheritor-retention play (transmission = churn
cliff). Cheap, high-value, uses existing tables.

### B8. Platform parity signals
Aladdin Wealth shipped AI per-client commentary (Oct 2025, Morgan Stanley first);
Morningstar's AI assistant turns statements into proposals and preps meeting briefs.
Our audit-pack + narration architecture is the same pattern at boutique scale —
independently validated design.

### B9. Data rails (kept within this book — per-client consent, not a rollout)
**Account Aggregator**: SEBI added MF/demat data in 2022; 780+ FIs live; wealth is
the fast-growing second use case. With a client's consent, AA adds *held-away* assets
and bank flows → completes PROFILE (income, spending capacity, external portfolios)
without any PDF. MF Central/CAS remains the manual fallback. This is the natural
"chapter 2" of the demo: *what we could see with your consent*.

### B10. Compliance rails (hard constraints on the engine)
MFD scope = **incidental advice**: basic, product-fact-based, limited to MF schemes
distributed, goal-based investing explicitly allowed (AMFI FAQ); **no advisory fees**,
no "adviser/wealth manager" nomenclature, RIA needed beyond MF schemes. 2025 update:
AMFI requires **records of advisory interactions for audit** — our advice ledger is
literally this, a compliance asset. The MFD-RIA boundary is under SEBI working-group
review → design the engine so every output is (a) scheme-fact-based, (b) suitability-
documented, (c) RM-approved before client contact. The Value Statement reports
*realized history* (not advice) — clean.

## C. Additions to the build (spec deltas)

1. **`build_value_statement.py`** — per client, per year: realized behavioural saves
   (prevented-panic events once call outcomes are logged; historical counterfactuals
   until then, labelled), tax harvested, fee savings executed, rebalancing effects.
   Output = the Value Statement section of the Audit Pack + a book-level total for
   chapter 6. *The business-model artifact.*
2. **`build_tax_harvest.py`** — per client, per FY: gain-harvest headroom left in the
   ₹1.25L exemption, loss-harvest candidates net of the sequencing rule, carry-forward
   ledger with ITR-deadline flag, exact lots to sell and re-buy. Runs off wealth.lots.
3. **Freak-out score** — add to PREDICT: P(panic) per client from profile features
   (MIT precedent), armed only during drawdowns; nudge scripts follow the one-action
   rule and persona framing.
4. **Household roll-up** — family_group aggregation + succession-risk flags in the
   book view and client page header.

Deferred (data or volume we don't have yet): AA ingestion, goals/IPS engine, uplift
models (need outcome volume), Bloat Check document ingestion, formal RCTs.

## Sources

Advisor value: [Vanguard Advisor's Alpha](https://www.vanguard.ca/content/dam/intl/americas/canada/en/documents/gas/advisors-alpha-infographic.pdf) · [Vanguard 2022 study PDF](https://e2djuwbzkni.exactdn.com/wp-content/uploads/2024/03/Vanguard-Study-on-3.0-Value-from-Advisors-7-2022.pdf) · [InvestmentNews on coaching](https://www.investmentnews.com/practice-management/advisors-continue-to-shine-as-emotional-circuit-breakers-vanguard-says/259609) · [Morningstar Gamma paper](https://www.morningstar.com/content/dam/marketing/shared/research/foundational/677796-AlphaBetaGamma.pdf) · [Kitces on Gamma](https://www.kitces.com/blog/morningstar-tries-to-quantify-the-value-of-financial-planning-1-8-gamma-for-retirees/)
Behavioural academia: [Calvet-Campbell-Sodini "Down or Out"](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=881768) · [Barber-Odean survey](https://faculty.haas.berkeley.edu/odean/papers%20current%20versions/behavior%20of%20individual%20investors.pdf) · [Campbell "Household Finance"](https://scholar.harvard.edu/files/campbell/files/householdfinance_jof_2006.pdf) · [Guiso-Sodini handbook](https://www.eief.it/files/2014/01/guiso_sodini-household-finance-an-emerging-field.pdf)
Panic & nudges: [When Do Investors Freak Out?](https://www.researchgate.net/publication/357274381_When_Do_Investors_Freak_Out_Machine_Learning_Predictions_of_Panic_Selling) · [IKEA-effect nudge](https://www.sciencedirect.com/science/article/abs/pii/S2214635021000460) · [Framing & panic (Risks 2024)](https://doi.org/10.3390/risks12100162) · [13M-person nudge RCT (PNAS)](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11789030/)
Tax India: [DealPlexus harvesting](https://www.dealplexus.com/blog/tax-loss-harvesting-india) · [JM Financial LTCG strategies](https://www.jmfinancialservices.in/blogs-and-articles/how-to-save-long-term-capital-gain-ltcg-tax-on-shares-in-india) · [Jiraaf tax harvesting](https://www.jiraaf.com/blogs/taxation/tax-harvesting) · [Finedge explainer](https://www.finedge.in/blog/mutual-funds/tax-harvesting-explained-mutual-funds)
Platforms: [Aladdin Wealth](https://www.blackrock.com/aladdin/products/aladdin-wealth) · [Aladdin AI commentary launch](https://www.morningstar.com/news/business-wire/20251002577295/aladdin-wealth-launches-ai-enabled-commentary-tool-for-wealth-advisors-morgan-stanleys-portfolio-risk-platform-first-to-implement) · [Morningstar advisor segment](https://www.morningstar.com/business/segments/advisors-wealth-managers)
NBA/uplift: [BCG NBA science](https://www.bcg.com/publications/2026/the-science-behind-next-best-action-programs) · [Grid Dynamics NBA](https://www.griddynamics.com/blog/next-best-action-churn-prevention) · [Life-event prediction (DSS)](https://www.sciencedirect.com/science/article/abs/pii/S0167923619302611)
India rails & rules: [AA 2026 guide](https://hyperverge.co/blog/account-aggregator-framework-rbi/) · [AA FY26 volumes](https://investmentguruindia.com/newsdetail/india-s-account-aggregator-ecosystem-facilitates-nearly-3-8-crore-financial-services-in-fy26311603) · [Value Research on incidental advice](https://www.valueresearchonline.com/stories/200465/mutual-fund-distributors-can-t-offer-incidental-advice-asserts-sebi/) · [AMFI MFD do's & don'ts FAQ](https://www.amfiindia.com/Themes/Theme1/downloads/FAQsonRoleofMFDsAdvts.pdf) · [SEBI MFD-RIA working group](https://www.5paisa.com/news/sebi-working-group-tackles-mfd-ria-overlap) · [SIP stoppage 2026 data](https://www.finnovate.in/learn/blog/sip-stoppage-ratio-stability-stagnation-2026) · [SIP discontinuation study](https://joirem.com/wp-content/uploads/journal/published_paper/volume-04/issue-3/J_EWXd444F.pdf)
Goals/glidepaths: [FPA goals-based value](https://www.financialplanningassociation.org/article/journal/JUN15-value-goals-based-financial-planning) · [Amundi Lifecycle Remix 2026](https://research-center.amundi.com/article/lifecycle-remix-glidepaths-personalisation-and-private-assets)
