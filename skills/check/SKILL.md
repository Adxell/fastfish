---
name: check
description: Quick conventions check - verifies the current changes (or a given path) follow the project's own skills, CLAUDE.md/AGENTS.md, rules files and architecture docs, using one fresh-context goldfish. Use when the user asks whether code follows the project's architecture, patterns or how-to-code rules.
argument-hint: "[path...]"
allowed-tools: Bash(python3:*), Read, Agent
---

# fastfish check

Arguments: `$ARGUMENTS`

!`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/project_map.py" map`

!`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/project_map.py" scope "$ARGUMENTS"`

If either block above is empty or shows a raw command, run those two commands yourself with Bash first.

## Steps

1. If `SCOPE_KIND=empty`, say there is nothing to check and stop.
2. Spawn one `fastfish:rules-fish` agent (or `rules-fish`) with this task, written out in full:

   ```
   Check target: <one line>
   Project root: <absolute path>
   Project map: <root>/.fastfish/project-map.md  (read it first)

   <paste the "Review scope" and "Guides that apply" sections verbatim>
   ```

3. Relay the result in chat: the `Guides used` line, then each finding as one line (`severity · path:line · rule · fix`). If there are no findings, say so in one line. Offer to fix them. No report file is needed unless the user asks.
