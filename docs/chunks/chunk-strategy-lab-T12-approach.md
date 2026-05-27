# Chunk: Strategy Lab Task 12 — Groq Insight Feed

## Data scale
No database queries needed. This module is purely LLM I/O: it takes in-memory
dicts (parameter_importance, top_genome_deltas) and calls the Groq API.

## Chosen approach
Mirror `atlas/signals/narrative.py` exactly:
- `openai.OpenAI(base_url="https://api.groq.com/openai/v1", api_key=GROQ_API_KEY)`
- `llama-3.3-70b-versatile`, temperature 0.3, max_tokens 400
- Sync (not async) — optimizer pipeline is a nightly batch job, not a web request
- `_get_groq_client()` as named in spec (different from `_get_client()` in narrative.py)

## Wiki patterns checked
- `LLM Provider Fallback Chain` — single Groq call is fine for nightly batch; no cascade needed at this volume
- `LLM Payload Size vs Context Window` (staging) — prompt is tiny (~500 tokens); 413 risk negligible

## Existing code reused
- `atlas/signals/narrative.py` — exact client construction pattern
- `structlog` for logging (already project-wide)

## Edge cases
- `GROQ_API_KEY` missing: `_get_groq_client` will construct client with empty key; Groq will
  return 401 which becomes an Exception caught by the outer try/except → returns []
- Malformed LLM response (no numbered bullets): bullet filter yields [] — graceful degradation
- Empty `parameter_importance` or `top_genome_deltas`: prompt still renders (shows empty JSON)
- LLM returns > 6 bullets: sliced to [:6]
- openai SDK not installed: RuntimeError from _get_groq_client → caught → returns []

## Expected runtime
- Single Groq API call: ~2-4s on t3.large (network bound, not CPU)
- Called once per nightly optimization run — no throughput concern

## Files
- `atlas/trading/insight.py` (new, <120 lines)
- `tests/trading/test_insight.py` (new, 3 tests)
