---
name: review
description: Fast goldfish review of the current changes, a file, a folder or a design doc. Builds/reuses a cached project map, then runs fresh-context reviewers in one parallel wave (design, code fit, project rules from the repo's own skills and CLAUDE.md). Use when the user asks to review, check or critique their work with fresh eyes.
argument-hint: "[path...] [--quick | --full | --deep] [--lenses=design,code,rules]"
allowed-tools: Bash(python3:*), Read, Write, Agent
---

# fastfish review

Arguments: `$ARGUMENTS`

## Project context (precomputed)

!`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/project_map.py" map`

!`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/project_map.py" scope "$ARGUMENTS"`

If either block above is empty or shows a raw command instead of output, run those two commands yourself with Bash (same arguments) before continuing.

## Steps

Keep this fast: no questions to the user, no stages, one wave of reviewers.

1. **Empty scope**: if `SCOPE_KIND=empty`, tell the user there is nothing to review (no changes, no target) and how to pass one (`/fastfish:review src/billing` or `/fastfish:review docs/design.md`). Stop.

2. **Pick lenses** (unless `--lenses=` is given):
   | Scope | Lenses |
   | --- | --- |
   | `docs` (a design doc or plan) | design-fish, code-fish, rules-fish |
   | `code` or `mixed`, ≤ 3 files (small change) | **quick by default**: code-fish, rules-fish, tell them "max 6 file reads" |
   | `code` or `mixed`, larger | design-fish, code-fish, rules-fish |
   | `--quick` | rules-fish + code-fish, max 1 each, tell them "max 8 file reads" |
   | `--full` | ignore the small-change shortcut; use the row for larger scopes |
   | `--deep` | all three, plus a second design-fish told to argue for a simpler design |

   Drop rules-fish only if the guides list says `none` **and** the scope is a doc.

3. **Spawn all lenses in a single message** (parallel `Agent` calls). The subagent type is `fastfish:<lens>` (use `<lens>` alone if the namespaced name is not registered). Give each one the same task, written out in full, because the goldfish has no memory of this conversation:

   ```
   Review target: <what the user asked to review, one line>
   Project root: <absolute path>
   Project map: <root>/.fastfish/project-map.md  (read it first)

   <paste the "Review scope" and "Guides that apply" sections verbatim>

   For uncommitted changes, view the diff by reading the changed files; focus on the changed parts.
   ```

   Do **not** add your own opinions, the conversation history or what the author intended. A goldfish only sees what is written.

4. **Merge** once all reviewers return. A reviewer that failed or returned nothing is `not run`, not "no findings". Drop duplicates (keep the one with the best evidence). Drop findings you can disprove in one quick look at the cited line. Check only the cited lines of blockers and majors; do not re-review the code yourself, the reviewers already did. Order by severity: blocker, major, minor.

5. **Write the report** to `.fastfish/reviews/<TIMESTAMP>-<short-slug>.md` (TIMESTAMP from the scope block):

   ```markdown
   # fastfish review: <target>

   Scope: <n files, source> · Lenses: <lens: completed | not run, ...> · Guides used: <paths>

   ## Blockers
   ### <title> (<lens>)
   - Where / Problem / Evidence or Rule / Fix

   ## Major
   ## Minor
   ```

   If the write is denied, put the full report in chat instead and say it was not saved.

6. **Reply in chat** with a short summary: the counts by severity, the top 3 findings one line each with `path:line`, and the report path. Then offer to fix the blockers and majors. Do not apply fixes until the user says so.
