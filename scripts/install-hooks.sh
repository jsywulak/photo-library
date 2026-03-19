#!/usr/bin/env bash
set -euo pipefail

HOOKS_DIR="$(git rev-parse --show-toplevel)/.git/hooks"

cat > "${HOOKS_DIR}/pre-commit" << 'EOF'
#!/usr/bin/env bash
set -euo pipefail

if ! command -v gitleaks &>/dev/null; then
  echo "gitleaks not found — run: brew install gitleaks" >&2
  exit 1
fi

gitleaks protect --staged --redact --exit-code 1
EOF

chmod +x "${HOOKS_DIR}/pre-commit"
echo "Installed pre-commit hook: gitleaks secret scanning"
