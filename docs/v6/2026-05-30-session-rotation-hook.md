# Session Context Rotation — design + ready-to-install hook

**Your ask:** "start new sessions after 60% of the context window is filled — how do we ensure that?"

## The honest constraints

- There is **no native "fire at 60% context" trigger** in Claude Code. The harness
  auto-compacts only when context is *nearly* full (~well above 60%).
- Hooks fire on *events* (UserPromptSubmit, Stop, PreCompact, SessionStart), not on
  a context-percentage threshold. But a `UserPromptSubmit` hook receives the
  transcript path, so it can *measure* current usage and *nudge* at 60%.
- A hook cannot force a new session by itself. The realistic mechanism is:
  **measure → warn at 60% → auto-`/handoff` and instruct rotation at 75%.**

## Recommended mechanism (3 layers)

| Layer | Trigger | Action |
|---|---|---|
| 1. Soft nudge | UserPromptSubmit, usage ≥ 60% | Inject reminder: "context 62% — wrap to a checkpoint soon" |
| 2. Hard handoff | UserPromptSubmit, usage ≥ 75% | Inject directive: "STOP feature work. Run the `remember`/`handoff` skill now, then tell the user to `/clear` and resume." |
| 3. Manual | You, anytime | `/compact` (summarize-in-place) or the `handoff` skill at a clean phase boundary |

60% is the *warn* line, 75% is the *act* line. Warning at 60% and acting at 60%
would rotate too aggressively (you lose a working session at the point it's most
warmed up). The 60→75 band lets the current phase finish cleanly.

## Ready-to-install hook

`~/.claude/hooks/context-budget-nudge.sh` (user-level, applies to all projects):

```bash
#!/usr/bin/env bash
# UserPromptSubmit hook: estimate context utilization from the transcript and
# nudge toward rotation. Reads the JSON payload on stdin; transcript_path points
# at the session .jsonl. Token estimate = bytes/4 heuristic (fast, no tokenizer).
set -euo pipefail
PAYLOAD=$(cat)
TRANSCRIPT=$(printf '%s' "$PAYLOAD" | python3 -c "import json,sys;print(json.load(sys.stdin).get('transcript_path',''))" 2>/dev/null || true)
[ -z "$TRANSCRIPT" ] || [ ! -f "$TRANSCRIPT" ] && exit 0

# Opus/Sonnet 4.x context window ~200k tokens. Tune if your plan differs.
WINDOW=200000
BYTES=$(wc -c < "$TRANSCRIPT" 2>/dev/null || echo 0)
EST_TOKENS=$(( BYTES / 4 ))
PCT=$(( EST_TOKENS * 100 / WINDOW ))

if [ "$PCT" -ge 75 ]; then
  echo "CONTEXT BUDGET: ~${PCT}% used. STOP starting new feature work. Finish the current step, then invoke the remember/handoff skill to write a continuation doc and tell the user to /clear and resume from it."
elif [ "$PCT" -ge 60 ]; then
  echo "CONTEXT BUDGET: ~${PCT}% used. Approaching rotation. Aim to reach a clean checkpoint (committed + verified) within the next few steps, then consider /compact or a handoff."
fi
exit 0
```

Wire it in `~/.claude/settings.json`:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      { "hooks": [ { "type": "command", "command": "bash ~/.claude/hooks/context-budget-nudge.sh" } ] }
    ]
  }
}
```

The hook's stdout is injected as context the assistant sees on each turn — so at 60%
I start steering toward a checkpoint; at 75% I hand off.

## Why bytes/4 instead of a real tokenizer

The hook runs on every prompt; it must be fast (<50ms). `bytes/4` is a well-known
approximation for English+code and is plenty accurate for a threshold nudge. If you
want precision later, swap in `tiktoken` — but it adds ~200ms/turn, not worth it for
a soft gate.

## Caveats

- The `WINDOW=200000` constant must match your actual model's window. Opus 4.8 /
  Sonnet 4.6 are 200k. If a larger-context tier is enabled, bump it.
- The byte heuristic *overcounts* slightly (JSON overhead, tool schemas) — which is
  the safe direction (rotates a touch early, never late).
- This is a *nudge*, not enforcement. The assistant still decides when to actually
  hand off. If you want hard enforcement, the Stop hook can block completion until a
  handoff doc exists — but that's heavier and can interrupt mid-thought. Start with
  the nudge.

## Install decision

I did **not** auto-install this tonight — editing `~/.claude/settings.json` mid-session
changes hook behavior for the running session and is the kind of outward-facing config
change I confirm first. Say the word and I'll drop the script + settings entry in one
step next session.
