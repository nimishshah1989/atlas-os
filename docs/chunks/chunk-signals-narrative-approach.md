# Chunk: Signals Narrative Generator (Task 6)

## Objective
Implement `atlas/signals/narrative.py` — a Groq Llama 3.3 70B narrative generator
that produces a one-paragraph investment brief from a structured context dict.

## Data scale
Not applicable — no database reads. Pure LLM call with structured prompt.

## Chosen approach

### SDK: openai (not groq)
The task spec shows `from groq import Groq` but `groq` SDK is NOT installed on this
machine. The project already uses `openai` SDK pointed at Groq's OpenAI-compatible
API (`https://api.groq.com/openai/v1`) — see `atlas/agents/specialists/base.py`
`_make_groq_client()`. This is the established pattern; we follow it.

The narrative.py will expose `_get_client()` returning an `OpenAI` instance with
Groq base URL, matching the existing pattern. Tests mock `_get_client` the same way.

### Pattern reuse
- `_make_groq_client()` from `atlas.agents.specialists.base` — copied inline to avoid
  cross-context import (bounded context rule: `atlas.signals` cannot import from
  `atlas.agents`)
- Same model/token constants as base.py (`llama-3.3-70b-versatile`, 300 max tokens)

### async wrapping
`generate_narrative` is `async def` but the Groq/OpenAI client is sync. The
function calls the sync client directly (same pattern as `call_groq` in base.py
which uses `asyncio.run_in_executor`). For this use case, direct sync call inside
async def is acceptable (FastAPI routes call it with await; since there's no
`asyncio.sleep` or yield, the event loop blocks only for the LLM latency window,
which is acceptable at Atlas volume).

## Wiki patterns checked
- Groq usage: `atlas/agents/specialists/base.py` — openai SDK + base_url pattern

## Edge cases handled
- Missing conviction_score → "not available" line
- Missing cts_state → "not available" line
- Missing rs_rank/rs_rank_total/rs_percentile → "not available" line
- LLM failure → structured fallback string (no bare except — uses `except Exception:`)

## Expected runtime
- LLM call: 1-3 seconds at Groq (fast inference)
- Prompt build: <1ms
- Test suite: <1 second (mocked)

## Files
- `atlas/signals/narrative.py` (new)
- `tests/unit/signals/test_narrative.py` (new)
