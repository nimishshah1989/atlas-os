# Chunk: Task 1.5 — Stock detail cross-link every token

## Tokens found (pre-implementation audit)

### StockDeepDiveHeader.tsx
- `SectorBadge` (line 32) — already renders as `<Link>` to `/sectors/[name]`. NO change needed.
- `IndexBadge` (lines 33-35) — renders "Nifty 50" / "Nifty 100" / "Nifty 500" as plain `<span>`. MUST become linked.
  - Target: `/sectors/Nifty%2050`, `/sectors/Nifty%20100`, `/sectors/Nifty%20500` — these are not sector pages. Better: link to the stocks page filtered by index. BUT the stocks page has no `?index=` query param support (client-side filtering only). The right URL is the stocks page `/stocks` which IS the index page — linking a plain label to `/stocks` is not meaningful. Real option: there is no dedicated index page. The connection rule says "index labels linked appropriately" — since no `/indices/[name]` route exists, we render with `<IndexBadge>` but can NOT genuinely link. Document as a token that cannot be linked (no route).
  - Revised: wrap in a `LinkedIndex` inline component that href-encodes to `/stocks?index=nifty_50` etc., but only if the stocks page supports it. It does NOT. So these are unlinked tokens — valid reason.

### MasterStateCard.tsx
- State label (`data-testid="state-label"`) — plain `<div>`. MUST get a tooltip explaining engine_state. Use `InfoTooltip` + `METRIC_REGISTRY['engine_state'].definition`.
- "N peers in this state today" text (peerLine, line 149-151) — plain `<div>`. MUST become a link to `#within-state-peers` anchor (on-page anchor to `WithinStatePeers` section).
  - `peerRank != null` branch: "Ranked #N of M today" → only rank phrase isn't a nav link; the count M should link to the peer table.
  - `peerRank == null` branch: "N peers in this state today" → the whole phrase links to the peer table.

### WithinStatePeers.tsx
- Peer symbol cells (line 91) — plain `{p.symbol}`. MUST become `<LinkedTicker symbol={p.symbol} />`.

## Approach

1. `WithinStatePeers.tsx`: add `data-testid="within-state-peers"` to the `<section>` (already exists) — no change needed for the anchor target. Import `LinkedTicker`, replace `{p.symbol}` in the table cell.

2. `MasterStateCard.tsx`:
   - Import `InfoTooltip` from `@/components/ui/InfoTooltip`.
   - Import `metric` from `@/lib/metric-registry` and get `engine_state` definition.
   - Wrap state label div with an inline flex row: `<div>{label}<InfoTooltip content={metric('engine_state')!.definition} /></div>`.
   - Peers line: wrap in `<a href="#within-state-peers">` (a plain anchor — no router needed for same-page anchor).

3. `StockDeepDiveHeader.tsx`: No change needed — `SectorBadge` already links. Index badges cannot be linked (no route). Document explicitly.

## Tooltip system choice

The page uses `InfoTooltip` from `@/components/ui/InfoTooltip` (Radix-based). `MasterStateCard` has no existing tooltip. `METRIC_REGISTRY` has `engine_state` with full definition. Using `InfoTooltip` + `metric('engine_state')` is consistent with the pattern in `ComponentScorecard` and `ComponentValidationRow`.

## Tests to write

File: `frontend/src/components/stocks/__tests__/StockDetailTokens.test.tsx`

- `WithinStatePeers`: peer symbols render as `<a>` links to `/stocks/[symbol]`
- `MasterStateCard`: state label row has an `<a>` with aria-label "info" (InfoTooltip trigger)
- `MasterStateCard`: peers count renders as a link to `#within-state-peers`
- Regression: existing `WithinStatePeers` and `MasterStateCard` tests still pass

## Files touched

- `frontend/src/components/stocks/WithinStatePeers.tsx`
- `frontend/src/components/stocks/MasterStateCard.tsx`
- `frontend/src/components/stocks/__tests__/StockDetailTokens.test.tsx`

## Files NOT touched

- `StockDeepDiveHeader.tsx` — SectorBadge already linked, index badges have no target route
- `StockDeepDiveBody.tsx` — no sector/index/peer tokens rendered in body (metric charts only)
- `metric-registry.ts` — `engine_state` already in registry, no new entries needed

## Index badge decision

"Nifty 50", "Nifty 100", "Nifty 500" labels in `StockDeepDiveHeader` are unlinked. Reason: no `/indices/[name]` route exists in the app. The stocks page has no `?index=` filter. Linking to `/stocks` would be misleading (shows all stocks, not filtered). This is a genuine reason — the token cannot be meaningfully linked without a new route.
