#!/usr/bin/env bash
# Runs eval cases the way a user would: scaffold a scratch copy of tinyshop, run
# Claude headless in it, then grade the answer. No sandbox needed.
#
#   ARM=fastfish  (default) fastfish as installed
#   ARM=plain     fastfish disabled: plain Claude, same prompt
#   ARM=egm       fastfish disabled, elephant-goldfish loaded from EGM_DIR (not installed)
#
# Usage: [ARM=..] [EGM_DIR=..] evals/run_local.sh [out_dir] [case...]
set -uo pipefail
EVALS="$(cd "$(dirname "$0")" && pwd)"
ARM="${ARM:-fastfish}"
OUT="${1:-$EVALS/results/local-$(date +%Y%m%d-%H%M%S)}"; shift || true
CASES=("$@"); [ ${#CASES[@]} -eq 0 ] && CASES=($(cd "$EVALS" && ls -d */case.yaml | xargs -n1 dirname))
OUT="$OUT/$ARM"; mkdir -p "$OUT"
TOOLS='Skill Agent Read Grep Glob Bash(python3:*) Bash(git:*) Write Edit'
EXTRA=()
case "$ARM" in
  fastfish) ;;
  plain) EXTRA=(--settings '{"enabledPlugins":{"fastfish@fastfish":false}}') ;;
  egm) EXTRA=(--settings '{"enabledPlugins":{"fastfish@fastfish":false}}' --plugin-dir "${EGM_DIR:?set EGM_DIR to an elephant-goldfish-model checkout}") ;;
  *) echo "unknown ARM=$ARM" >&2; exit 2 ;;
esac

run_case() {
  local c=$1 ws="$OUT/$1/workspace" prompt
  mkdir -p "$ws" && (cd "$ws" && git init -q && bash "$EVALS/$c/scaffold.sh")
  prompt=$(python3 -c 'import re,json,sys; print(json.loads(re.search(r"^  prompt: (.*)$", open(sys.argv[1]).read(), re.M).group(1)))' "$EVALS/$c/case.yaml")
  # EGM's skills are user-invoked only, so call its review loop explicitly and ask it not to pause.
  [ "$ARM" = egm ] && [ "$c" != no-fire-explain ] && prompt="/egm:egm-review-loop $prompt Do not ask me questions or wait for confirmation: use your defaults, run one full round and give the findings in your reply."
  local start=$(date +%s)
  (cd "$ws" && timeout 1500 claude -p "$prompt" --allowedTools $TOOLS "${EXTRA[@]}" --output-format json > "$OUT/$c/result.json" 2> "$OUT/$c/stderr.txt")
  echo $(( $(date +%s) - start )) > "$OUT/$c/seconds"
}
for c in "${CASES[@]}"; do run_case "$c" & done
wait
python3 "$EVALS/grade_local.py" "$OUT" "$ARM"
