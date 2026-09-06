#!/bin/bash
# SessionStart hook — make a fresh Claude Code on the web session able to lint, test and use the
# team tooling (graphify, gstack, headroom). Runs only in remote sessions, synchronously, and every
# step is best-effort: a network blip must never block a session. Idempotent.
set -uo pipefail

# Pinned supply chain — bump deliberately; the hook runs with repo access and env secrets in
# every cloud session, so an unpinned `main` / latest-PyPI install is arbitrary code run with
# our keys. What is installed today: `uv tool list`, `git -C ~/.claude/skills/gstack rev-parse HEAD`.
GSTACK_COMMIT=0d1bd5616c0ef096bb7ccee336f63c60ee408618  # gstack v1.79.0.0 (releases are untagged)
GRAPHIFY_VERSION=0.9.53
HEADROOM_VERSION=0.37.0

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}"
export PATH="$HOME/.local/bin:$HOME/.bun/bin:$PATH"
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo 'export PATH="$HOME/.local/bin:$HOME/.bun/bin:$PATH"' >> "$CLAUDE_ENV_FILE"
fi

log() { echo "[session-start] $*"; }

# 1. Python toolchain — `make gate` needs BOTH extras, exactly as CI installs them:
# dev for the tooling (ruff, pytest, pyright), global for the global-market imports the
# unit tests and the pyright ratchet resolve (openpyxl via providers/ssga.py). `uv sync` is
# exact, so an extra that is not asked for is not installed and collection fails.
if command -v uv >/dev/null 2>&1; then
  if uv sync --extra dev --extra global -q; then log "uv sync ok"; else log "uv sync FAILED (continuing)"; fi
else
  log "uv not found — skipping python setup"
fi

# 2. graphify + headroom CLIs (uv tool installs are isolated; safe to re-run).
if ! command -v graphify >/dev/null 2>&1; then
  if uv tool install -q "graphifyy==$GRAPHIFY_VERSION"; then log "graphify $GRAPHIFY_VERSION installed"; else log "graphify install FAILED"; fi
fi
if ! command -v headroom >/dev/null 2>&1; then
  if uv tool install -q --python 3.13 "headroom-ai[all]==$HEADROOM_VERSION"; then log "headroom $HEADROOM_VERSION installed"; else log "headroom install FAILED"; fi
fi

# 3. Code knowledge graph (gitignored, ~10s, AST only — no LLM, nothing leaves the machine).
if command -v graphify >/dev/null 2>&1 && [ ! -f graphify-out/graph.json ]; then
  if timeout 300 graphify update . --no-cluster >/dev/null 2>&1; then log "graphify graph built"; else log "graphify build FAILED"; fi
fi

# 4. gstack — global install at $GSTACK_COMMIT, skills symlinked into ~/.claude/skills (needs bun;
#    ./setup also downloads a headless Chromium for /browse, so the first run takes a couple of
#    minutes). A depth-1 clone of main need not contain the pin, so fetch the SHA itself (GitHub
#    serves any reachable commit) and fall back to a full clone + checkout if that is refused.
GSTACK_DIR="$HOME/.claude/skills/gstack"
GSTACK_REPO=https://github.com/garrytan/gstack.git
fetch_gstack_pin() {
  rm -rf "$GSTACK_DIR" && mkdir -p "$GSTACK_DIR" \
    && git -C "$GSTACK_DIR" init -q \
    && git -C "$GSTACK_DIR" remote add origin "$GSTACK_REPO" \
    && git -C "$GSTACK_DIR" fetch -q --depth 1 origin "$GSTACK_COMMIT" \
    && git -C "$GSTACK_DIR" checkout -q FETCH_HEAD
}
clone_gstack_pin() {
  rm -rf "$GSTACK_DIR" \
    && git clone -q "$GSTACK_REPO" "$GSTACK_DIR" \
    && git -C "$GSTACK_DIR" checkout -q "$GSTACK_COMMIT"
}
if [ ! -d "$GSTACK_DIR/bin" ]; then
  if { fetch_gstack_pin || clone_gstack_pin; } 2>/dev/null \
     && [ "$(git -C "$GSTACK_DIR" rev-parse HEAD 2>/dev/null)" = "$GSTACK_COMMIT" ] \
     && (cd "$GSTACK_DIR" && timeout 600 ./setup -q --no-team >/dev/null 2>&1); then
    log "gstack installed @ ${GSTACK_COMMIT:0:8}"
  else
    log "gstack install FAILED (skills unavailable this session)"
  fi
fi

# 4b. gstack verify gate — a Stop hook that refuses to end a turn while `make gate` (declared in
#     CLAUDE.md as `gstack:verify:`) is red; this is the "loop until the goal is green" mechanism.
#     Registration is global (~/.claude/settings.json); trust is per repo and audit-logged.
G="$GSTACK_DIR/bin"
if [ -x "$G/gstack-verify-gate" ] && [ -x "$G/gstack-settings-hook" ]; then
  "$G/gstack-settings-hook" add-event --event Stop --command "$G/gstack-verify-gate" --source verify-gate >/dev/null 2>&1 || true
  "$G/gstack-verify-gate" --trust >/dev/null 2>&1 && log "verify gate armed (make gate)" || log "verify gate trust FAILED"
fi

# 5. headroom MCP tools (the compression proxy itself is laptop-side: `headroom wrap claude`).
if command -v headroom >/dev/null 2>&1; then
  headroom mcp install --agent claude >/dev/null 2>&1 || true
fi

exit 0
