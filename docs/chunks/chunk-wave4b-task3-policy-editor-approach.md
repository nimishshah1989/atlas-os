# Chunk: Wave 4B Task 3 — PolicyEditor.tsx

## Data scale
Frontend-only task; no DB queries needed.

## Chosen approach
Presentational React component (no API calls). Mirrors PolicyPanel.tsx structure exactly.
- Same 7 groups (Deployment / Concentration / Entry / Exit / Instrument / Benchmark / Cadence)
- Same TOOLTIPS map + InfoTooltip (not MetricTooltip — policy fields are config, not metrics)
- Same FIELD_LABELS map
- Local React state (`useState`) tracks draft edits as `Partial<Record<keyof EffectivePolicy, PolicyFieldValue['value']>>`
- `isDirty`: derived from whether any draft field differs from the initial prop
- `onSave(changedFields)`: only changed fields passed, typed as `PolicyEditorChanges`

## Wire for each field kind
- `pct` / `rank` fields → `<input type="number">` with step precision
- `int` fields → `<input type="number" step="1">`
- `bool` → `<button>` toggle (Yes/No)
- `buy_states` → multi-select checkboxes for the 7 stage values
- `trailing_stop_pct` → number input + clear button (null = off)
- `instrument_universe` → `<select>` with 4 options
- `rebalance_cadence` → `<select>` (daily/weekly/monthly)
- `state_exit_trim` / `state_exit_full` → `<select>` of stage values
- `benchmark` → `<input type="text">`

## Portfolio mode
- Inherited fields: show greyed value + "Override" button → makes editable
- Overridden fields: show editable input + "Revert" button → sends explicit clear

## `onSave` contract
```ts
export type PolicyEditorChanges = Partial<{
  [K in keyof EffectivePolicy]: PolicyFieldValue['value'] | null
}>
```
- In `house-default` mode: all fields that differ from initial value
- In `portfolio` mode: only fields that are overridden (a reverted field is sent as `null` = explicit clear of override)

## Edge cases
- `trailing_stop_pct` can be null (cleared to "off") — sent as `null`
- `buy_states` empty array is a valid value (no buy states permitted)
- `respect_regime_cap` boolean must be serialized correctly
- Numbers from inputs come in as strings → parse before comparing to detect dirtiness

## LOC budget
PolicyEditor.tsx ≤ 350 LOC. Test ≤ 800 LOC.

## Wiki patterns checked
- InfoTooltip pattern from PolicyPanel.tsx (reused verbatim)
- userEvent.setup() pattern from ColumnToggle.test.tsx
- fireEvent pattern from RRGChart.test.tsx

## Existing code reused
- `TOOLTIPS`, `FIELD_LABELS`, `GROUPS` constants — copied from PolicyPanel, not re-exported (to keep PolicyPanel unchanged)
- `InfoTooltip` component
- `stageLabel`, `instrumentUniverseLabel` from stage-labels.ts
- `EffectivePolicy`, `PolicyFieldValue` types re-exported from PolicyPanel.tsx

## Expected runtime
Frontend-only; no compute.
