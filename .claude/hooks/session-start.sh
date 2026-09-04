#!/bin/bash
# SessionStart hook — make a fresh Claude Code on the web session able to lint, test and use the
# team tooling (graphify, gstack, headroom). Runs only in remote sessions, synchronously, and every
# step is best-effort: a network blip must never block a session. Idempotent.
set -uo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}"
export PATH="$HOME/.local/bin:$HOME/.bun/bin:$PATH"
if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo 'export PATH="$HOME/.local/bin:$HOME/.bun/bin:$PATH"' >> "$CLAUDE_ENV_FILE"
fi

log() { echo "[session-start] $*"; }

# 1. Python toolchain — `make gate` needs the dev extra (ruff, pytest, pyright).
if command -v uv >/dev/null 2>&1; then
  if uv sync --extra dev -q; then log "uv sync ok"; else log "uv sync FAILED (continuing)"; fi
else
  log "uv not found — skipping python setup"
fi

# 2. graphify + headroom CLIs (uv tool installs are isolated; safe to re-run).
if ! command -v graphify >/dev/null 2>&1; then
  if uv tool install -q graphifyy; then log "graphify installed"; else log "graphify install FAILED"; fi
fi
if ! command -v headroom >/dev/null 2>&1; then
  if uv tool install -q --python 3.13 "headroom-ai[all]"; then log "headroom installed"; else log "headroom install FAILED"; fi
fi

# 3. Code knowledge graph (gitignored, ~10s, AST only — no LLM, nothing leaves the machine).
if command -v graphify >/dev/null 2>&1 && [ ! -f graphify-out/graph.json ]; then
  if timeout 300 graphify update . --no-cluster >/dev/null 2>&1; then log "graphify graph built"; else log "graphify build FAILED"; fi
fi

# 4. gstack — global install, skills symlink into ~/.claude/skills (needs bun; ./setup also
#    downloads a headless Chromium for /browse, so the first run takes a couple of minutes).
if [ ! -d "$HOME/.claude/skills/gstack/bin" ]; then
  if git clone --single-branch --depth 1 -q https://github.com/garrytan/gstack.git "$HOME/.claude/skills/gstack" 2>/dev/null \
     && (cd "$HOME/.claude/skills/gstack" && timeout 600 ./setup -q --no-team >/dev/null 2>&1); then
    log "gstack installed"
  else
    log "gstack install FAILED (skills unavailable this session)"
  fi
fi

# 5. headroom MCP tools (the compression proxy itself is laptop-side: `headroom wrap claude`).
if command -v headroom >/dev/null 2>&1; then
  headroom mcp install --agent claude >/dev/null 2>&1 || true
fi

exit 0
