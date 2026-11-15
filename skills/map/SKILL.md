---
name: map
description: Build or refresh the fastfish project map (.fastfish/project-map.md) - stack, layout, entry points, test commands and every project guide (skills, CLAUDE.md, AGENTS.md, rules, architecture docs). Use when the user wants goldfish reviewers to understand the project, or to add team notes to the map.
argument-hint: "[--force] [notes to remember]"
allowed-tools: Bash(python3:*), Read, Write, Edit
---

# fastfish map

Arguments: `$ARGUMENTS`

1. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/project_map.py" map` (add `--force` if the arguments include it).
2. If the arguments contain notes (anything besides `--force`), append them as bullet points to `.fastfish/notes.md` (create it if needed), then run the command again so the map picks them up. Notes are for facts the scan cannot detect, for example "services/ must never import from api/" or "the legacy/ folder is frozen".
3. Read `.fastfish/project-map.md` and reply with a 4-6 line summary: stack, number of files, and which guides the goldfish will check against (skills by name). If no guides were found, suggest adding a `CLAUDE.md` or a `.claude/skills/<name>/SKILL.md` that describes the architecture, since that is what the rules checker enforces.
