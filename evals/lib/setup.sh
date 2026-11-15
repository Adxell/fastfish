# Sourced by each case's scaffold.sh: copies the clean tinyshop fixture into the
# run directory and commits it, so the case's own edits show up as uncommitted changes.
set -euo pipefail
EVALS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cp -R "$EVALS_DIR/fixtures/tinyshop/." .
git add -A >/dev/null
git -c user.name="Plugin Eval" -c user.email=eval@example.invalid commit -qm "tinyshop baseline" >/dev/null

# Commit extra baseline files a case adds before its uncommitted edit.
commit_base() {
  git add -A >/dev/null
  git -c user.name="Plugin Eval" -c user.email=eval@example.invalid commit -qm "${1:-baseline extras}" >/dev/null
}
