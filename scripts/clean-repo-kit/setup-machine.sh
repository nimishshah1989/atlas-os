#!/usr/bin/env bash
# Run ONCE per dev machine (Mac or Linux). Makes clean-by-default the behaviour of EVERY
# git repo you create or clone on this machine — no per-repo setup, forever. Idempotent.
#
#   bash setup-machine.sh
set -euo pipefail

# ── Layer 1: GLOBAL gitignore — universal junk ignored in EVERY repo, no per-repo entry ──
GI="$HOME/.gitignore_global"
cat > "$GI" <<'EOF'
# OS
.DS_Store
Thumbs.db
# Editors
.vscode/
.idea/
*.swp
*~
# Python
__pycache__/
*.py[cod]
.venv/
venv/
*.egg-info/
.ruff_cache/
.pytest_cache/
.mypy_cache/
# JS / web
node_modules/
.next/
dist/
build/
# Coverage / logs / env / secrets
.coverage
coverage.json
htmlcov/
*.log
.env
.env.local
EOF
git config --global core.excludesfile "$GI"
echo "✓ global gitignore active → $GI (every repo now ignores this junk)"

# ── Layer 2: pre-commit auto-installs in every new clone/init (if the repo has a config) ──
if command -v pre-commit >/dev/null 2>&1; then
  mkdir -p "$HOME/.git-template"
  git config --global init.templateDir "$HOME/.git-template"
  pre-commit init-templatedir "$HOME/.git-template" >/dev/null
  echo "✓ pre-commit will auto-install its hook in every future clone/init"
else
  echo "! pre-commit not found — run:  pipx install pre-commit   (or: brew install pre-commit)  then re-run this"
fi

echo ""
echo "Done. New repos inherit both layers automatically."
echo "For repos you already cloned, run once inside each:  pre-commit install"
