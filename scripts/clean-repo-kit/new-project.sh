#!/usr/bin/env bash
# Scaffold a NEW project that is clean by construction: git init + the portable guardrail
# kit (.gitignore, .pre-commit-config.yaml, Makefile `clean`, README) + activate hooks +
# first commit. Pairs with setup-machine.sh (global junk-ignore + auto-install).
#
#   bash new-project.sh my-app
set -euo pipefail
NAME="${1:?usage: new-project.sh <name>}"
mkdir -p "$NAME" && cd "$NAME"
git init -q

cat > .gitignore <<'EOF'
# Project-specific ignores go here. Universal junk (caches, node_modules, .venv, .DS_Store,
# .env) is handled once by your global ~/.gitignore_global — see clean-repo-kit/setup-machine.sh.
EOF

cat > .pre-commit-config.yaml <<'EOF'
# Portable hygiene pack — auto-cleans junk + blocks bad commits on every `git commit`.
# Fully self-contained (no global deps). Activate with:  pre-commit install
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-added-large-files
        args: [--maxkb=1024]
      - id: check-merge-conflict
      - id: check-case-conflict
      - id: check-yaml
      - id: check-json
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.21.2
    hooks:
      - id: gitleaks              # blocks committing secrets
EOF

cat > Makefile <<'EOF'
.PHONY: clean
# Surgical sweep of local disk junk. Deliberately never deletes .venv / node_modules / .next
# (on a live box those ARE the running app). Full reset on a dev machine only: git clean -fdX
clean:
	find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .ruff_cache \
	  -o -name .mypy_cache -o -name '*.egg-info' \) -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf .coverage coverage.json htmlcov 2>/dev/null || true
	@echo "swept caches (left .venv/node_modules/.next intact)"
EOF

printf '# %s\n\nScaffolded with the clean-repo kit.\n' "$NAME" > README.md

if command -v pre-commit >/dev/null 2>&1; then pre-commit install >/dev/null 2>&1 && echo "✓ pre-commit hooks active"; fi
git add -A && git commit -qm "chore: init clean-repo scaffold" && echo "✓ '$NAME' initialized clean"
