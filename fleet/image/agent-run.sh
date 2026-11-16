#!/usr/bin/env bash
# Entrypoint of a fastfish agent pod. Configured entirely by environment variables
# (set by `ff`, see fleet/fflib/manifests.py):
#   AGENT_NAME AGENT_MODE(task|review|interactive) REPO BASE BRANCH PROMPT TARGET PR MODEL MAX_TURNS FF_NOTIFY
#   CLAUDE_CODE_OAUTH_TOKEN or ANTHROPIC_API_KEY   (secret claude-auth)
#   GH_TOKEN                                       (secret git-auth, optional)
set -uo pipefail

OUT=/work/out
PLUGIN=/opt/fastfish
MODE="${AGENT_MODE:-task}"
NAME="${AGENT_NAME:-agent}"
WORK_BRANCH="ff/$NAME"
EXIT=0
PUSHED=""
PR_URL=""
NOTE=""
mkdir -p "$OUT"

log() { echo "[ff] $*"; }

finish() {
  # status.json goes to /work/out and to the termination log, which `ff ls` reads without exec.
  S_NAME="$NAME" S_MODE="$MODE" S_EXIT="$EXIT" S_BRANCH="$PUSHED" S_PR="$PR_URL" S_NOTE="$NOTE" \
  python3 - "$OUT/transcript.jsonl" <<'PY' > "$OUT/status.json"
import json, os, sys
result = {}
try:
    for line in open(sys.argv[1], encoding="utf-8", errors="replace"):
        if line.startswith("{"):
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("type") == "result":
                result = event
except OSError:
    pass
e = os.environ
print(json.dumps({
    "agent": e["S_NAME"], "mode": e["S_MODE"], "exit": int(e["S_EXIT"]),
    "branch": e["S_BRANCH"] or None, "pr_url": e["S_PR"] or None, "note": e["S_NOTE"][:300] or None,
    "turns": result.get("num_turns"), "cost_usd": result.get("total_cost_usd"),
}))
PY
  head -c 4000 "$OUT/status.json" 2>/dev/null >/dev/termination-log || true
  if [ -n "${FF_NOTIFY:-}" ]; then
    local word=done; [ "$EXIT" -ne 0 ] && word="failed ($EXIT)"
    curl -fsS -m 10 -d "fastfish agent $NAME $word ${PR_URL:-$PUSHED}" "$FF_NOTIFY" >/dev/null 2>&1 || true
  fi
  log "finished: exit=$EXIT ${PUSHED:+branch=$PUSHED} ${PR_URL:+pr=$PR_URL}"
  exit "$EXIT"
}

fail() { NOTE="$1"; EXIT="${2:-2}"; log "error: $1"; finish; }

run_claude() {
  local args=(-p "$1" --output-format stream-json --verbose
              --permission-mode bypassPermissions --plugin-dir "$PLUGIN"
              --max-turns "${MAX_TURNS:-200}")
  [ -n "${MODEL:-}" ] && args+=(--model "$MODEL")
  claude "${args[@]}" < /dev/null | tee "$OUT/transcript.jsonl"
  EXIT=${PIPESTATUS[0]}
}

commit_and_push() {
  git add -A
  git diff --cached --quiet || git commit -q -m "ff($NAME): ${PROMPT:-interactive session}" \
    -m "Made by fastfish agent $NAME."
  if [ "$(git rev-list --count "origin/$BASE..HEAD" 2>/dev/null || echo 0)" = 0 ]; then
    log "no changes to push"
    return
  fi
  if git push -q -u origin "$WORK_BRANCH"; then
    PUSHED="$WORK_BRANCH"
    log "pushed $WORK_BRANCH"
  else
    fail "git push failed (is GH_TOKEN set with write access?)" 3
  fi
  if [ "${PR:-0}" = 1 ]; then
    PR_URL=$(gh pr create --base "$BASE" --head "$WORK_BRANCH" \
      --title "ff($NAME): $(printf '%s' "${PROMPT:-interactive session}" | head -c 60)" \
      --body "Opened by fastfish agent \`$NAME\`.

Task:
$PROMPT" 2>&1 | tail -n1) || { NOTE="gh pr create failed: $PR_URL"; PR_URL=""; log "$NOTE"; }
  fi
}

# ---------------------------------------------------------------- setup

[ -n "${CLAUDE_CODE_OAUTH_TOKEN:-}${ANTHROPIC_API_KEY:-}" ] ||
  fail "no Claude credentials: create secret claude-auth (ff setup)"
[ -n "${REPO:-}" ] || fail "REPO is not set"

git config --global user.name "${GIT_AUTHOR_NAME:-fastfish agent}"
git config --global user.email "${GIT_AUTHOR_EMAIL:-fastfish-agent@users.noreply.github.com}"
git config --global init.defaultBranch main
if [ -n "${GH_TOKEN:-}" ]; then
  # Token stays in the environment; it is never written into the remote URL or .git/config.
  git config --global credential.helper \
    '!f() { test "$1" = get && echo username=x-access-token && echo "password=$GH_TOKEN"; }; f'
fi

log "agent $NAME ($MODE) cloning $REPO"
cd /work || fail "/work missing"
git clone -q "$REPO" repo || fail "git clone failed (private repo without GH_TOKEN?)"
cd repo
BASE="${BASE:-$(git symbolic-ref --short refs/remotes/origin/HEAD | sed 's#^origin/##')}"
git checkout -q "$BASE" || fail "base branch $BASE not found"

# ---------------------------------------------------------------- modes

case "$MODE" in
  task)
    git checkout -q -b "$WORK_BRANCH"
    log "working on $WORK_BRANCH from $BASE"
    [ -n "${PROMPT:-}" ] || fail "task mode needs PROMPT"
    run_claude "$PROMPT"
    commit_and_push
    ;;

  review)
    if [ -n "${TARGET:-}" ]; then
      [ -n "${BRANCH:-}" ] && { git checkout -q "$BRANCH" || fail "branch $BRANCH not found"; }
      ask="/fastfish:review $TARGET --full"
    elif [ -n "${BRANCH:-}" ]; then
      # Stage the branch's changes on top of the base as uncommitted changes, which is
      # exactly the scope /fastfish:review picks up by default.
      if git merge -q --squash --no-commit "origin/$BRANCH" >/dev/null 2>&1; then
        log "reviewing $BRANCH against $BASE"
      else
        git reset -q --hard && git checkout -q "$BRANCH" || fail "branch $BRANCH not found"
        log "$BRANCH does not merge cleanly into $BASE; reviewing its last commit instead"
      fi
      ask="/fastfish:review --full"
    else
      ask="/fastfish:review --full"
      log "no --branch or --target: reviewing the last commit on $BASE"
    fi
    run_claude "$ask"
    report=$(ls -t .fastfish/reviews/*.md 2>/dev/null | head -n1)
    if [ -n "$report" ]; then
      cp "$report" "$OUT/review.md"
      echo "[ff] ===== review report ====="
      cat "$report"
      echo "[ff] ===== end review report ====="
    else
      NOTE="no review report was written"
      log "$NOTE"
    fi
    ;;

  interactive)
    git checkout -q -b "$WORK_BRANCH"
    session=(claude --plugin-dir "$PLUGIN" --permission-mode acceptEdits)
    [ -n "${MODEL:-}" ] && session+=(--model "$MODEL")
    [ -n "${PROMPT:-}" ] && session+=("$PROMPT")
    if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
      # Pre-approve the key from the secret so the session does not open on a "use this key?" dialog.
      python3 - <<'PY'
import json, os
path = os.path.expanduser("~/.claude.json")
cfg = json.load(open(path)) if os.path.exists(path) else {}
approved = cfg.setdefault("customApiKeyResponses", {}).setdefault("approved", [])
approved.append(os.environ["ANTHROPIC_API_KEY"][-20:])
json.dump(cfg, open(path, "w"))
PY
    fi
    printf '#!/usr/bin/env bash\ncd /work/repo\nexec %s\n' "$(printf '%q ' "${session[@]}")" > /work/session.sh
    chmod +x /work/session.sh
    tmux new-session -d -s agent -x 200 -y 50 /work/session.sh || fail "tmux failed to start"
    log "interactive session ready on $WORK_BRANCH; attach with: ff attach $NAME"
    while tmux has-session -t agent 2>/dev/null; do sleep 5; done
    log "session ended"
    commit_and_push
    ;;

  *) fail "unknown AGENT_MODE=$MODE" ;;
esac

finish
