# 0003 — Monday confirmations: buys set target weights, and the book is frozen at publish

- **Status:** Accepted (2026-07-29)
- **Context chunk:** Monday confirmations (weekly model-PF buy/sell document)

## Context

The FM authors buy/sell calls for three model portfolios (Alpha, Passive,
India XI) every Monday in Excel and circulates the sheet; the team rebuilds the
model portfolios from it. Atlas now hosts that document: instrument autocomplete
over the real universe, auto-filled sectors, trigger/stop, attached chart
screenshots, evidence sections, and a printable per-portfolio report.

The flow was designed first in **niyam** (the SEBI-RIA platform). Niyam models it
as a `recommendation_universe` (week_of + PO-approval lifecycle) holding
8-dimension `universe_items`, then fans it out to ~269 client accounts as
content-hashed consent envelopes before any trade may fire. Niyam is not in
production (its prod DB is 31 migrations behind; broker/WhatsApp/Kite adapters
are mocks) and — critically — it has **no rendering of the FM's decision as a
document**. Atlas fills exactly that gap.

Two decisions here are non-obvious and each rejected a plausible alternative.

## Decision 1 — a buy states the position's TARGET weight, not an increment

A buy row's `weight_pct` is where the position should **end up**. Holding Biocon
at 8% and writing 12% makes it 12%, not 20%. A sell's `weight_pct` is the amount
**trimmed**; reaching zero exits. Cash is the implied remainder (100 − Σ).

*Rejected:* buy = "add this much". The FM's sheet lists the resulting Model PF
with one weight per name, and niyam's `model_items.target_weight` is likewise a
target — an increment reading would silently double positions on a top-up, the
single most common weekly action. The editor banner therefore reports **gross**
freed/deployed (a week that sells 12% and redeploys 8% must read that way, not
as a bare 4% net swing).

## Decision 2 — the book is folded once, at publish, and stored on the row

`mpf_confirmation.resulting_book` is a jsonb snapshot written inside the publish
transaction. Reads (sell-side prefill, sector pie, report, next week's opening
book) are a plain lookup of the latest published snapshot.

*Rejected:* deriving holdings at read time by replaying every published week
(the `portfolio_trades` precedent, where holdings are derived from fills). A
report is a circulated document: once posted to the group it must render
identically forever. Read-time derivation would let a later correction silently
rewrite the past, and it re-does the same work on every page load. Publish is
one-way for the same reason; the FM's Friday-draft → Monday-final habit is served
by editing the **draft**, not by unpublishing.

Consequences: `UNIQUE(portfolio_code, week_of)` makes week ordering total (no
tie-break needed), and publish revalidates server-side against the stored book,
so a stale editor tab cannot slip a sell past a position that is no longer there.

## Smaller choices worth recording

- **Weights fold in integer basis points.** postgres.js returns `numeric` as a
  string; float percentages drift over months of trims. Exits assert exactly 0.
- **`UNIQUE(confirmation_id, instrument_key)` IS the both-sides rule** — the FM's
  explicit requirement ("system should verify that the same instrument is not on
  Buy as well as sell side") is enforced by the database, not only the form. The
  save route maps the 23505 violation to a readable 409.
- **No `mpf_portfolio` master table.** Three static books = a CHECK constraint
  plus a TS display-name map; a fourth book is a one-line ALTER.
- **Chart screenshots as `bytea`.** A handful of images a week, backed up with
  the DB, no bucket or new dependency. Object storage is the upgrade path if
  volume grows.
- **PDF = print stylesheet + `window.print()`.** Zero new dependencies and the
  layout is exactly what is on screen. Uploads go through a route handler, never
  a server action (1 MB body cap). weasyprint (already used by niyam for fee
  statements) is the upgrade path if one-click server-side PDFs are ever wanted.
- **Sectors are snapshotted onto the call row at authoring** (niyam's rule) so a
  historical report never mutates when an instrument is reclassified.
