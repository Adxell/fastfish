# fastfish

Fresh-eyes reviews for Claude Code that are fast, know your project, and enforce **your project's own rules**.

Inspired by the [Elephant-Goldfish Model](https://github.com/google/elephant-goldfish-model): the main session (the elephant) holds the context, and reviewers (goldfish) start with no memory of the conversation, so they catch what the author assumed but never wrote down. fastfish keeps that idea and changes how it runs:

| | EGM | fastfish |
| --- | --- | --- |
| Review flow | 5 sequential stages with a question between each | One parallel wave, no questions |
| Orchestration | Elephant → synthesizer → goldfish | Elephant → goldfish (merged by the elephant) |
| Project understanding | Each goldfish explores the repo from scratch | A cached project map, built by a script in under a second |
| Standards | Generic document standards bundled in the plugin | The repo's own skills, CLAUDE.md, AGENTS.md, rules and architecture docs |
| Scope | Whole document | Changed files plus only the guides whose `paths`/`globs` match them |

## Install

```sh
claude plugin marketplace add Adxell/fastfish
claude plugin install fastfish@fastfish
```

Or from inside Claude Code: `/plugin marketplace add Adxell/fastfish`, then `/plugin install fastfish@fastfish`.

For local development, point the marketplace at a checkout instead: `claude plugin marketplace add /path/to/fastfish`.

Start a new session afterwards. Requires `python3` (stdlib only) and works best inside a git repo.

## Commands

| Command | What it does |
| --- | --- |
| `/fastfish:review [path...]` | Review uncommitted changes (or the last commit, or the given files/folders/doc). Picks lenses by scope and writes `.fastfish/reviews/<time>-<slug>.md`. |
| `/fastfish:review --quick` | Two lenses on a small read budget. |
| `/fastfish:review --deep` | All lenses plus a second design reviewer arguing for a simpler design. |
| `/fastfish:check [path...]` | Rules-only check: does this follow the project's architecture and how-to-code guides? |
| `/fastfish:map [--force] [notes]` | Rebuild the project map, or add team notes the scan cannot detect. |

## Starting a new project

fastfish is installed per user, so it works in any new project straight away. What matters is giving the goldfish rules to enforce: `rules-fish` only checks what is written down.

1. **Create the repo.** fastfish uses git to find what changed.

   ```sh
   mkdir ~/projects/my-app && cd ~/projects/my-app
   git init
   claude
   ```

2. **Write the rules before the code.** Add a root `CLAUDE.md` with the stack, the folder layout, the commands and the rules that apply everywhere. Put area-specific rules in scoped skills, for example `.claude/skills/backend/SKILL.md`:

   ```markdown
   ---
   name: backend-architecture
   description: Layering rules for the API.
   paths: ["internal/**", "cmd/**"]
   ---
   Handlers never touch storage directly; they go through a service.
   ```

   A skill with `paths:` is only checked when a changed file matches, so reviews stay focused.

3. **Review the design first.** Write the plan in `docs/design.md` and run `/fastfish:review docs/design.md`. Gaps in a plan are cheaper to fix than gaps in code.

4. **Build in small steps.** Ask Claude for one piece, run `/fastfish:review` (or `/fastfish:check` for rules only), fix what it finds, commit, repeat. Use `/fastfish:review --deep` before big merges.

5. **Keep the map honest.** The map rebuilds itself when files or guides change. Add facts the scan cannot see with `/fastfish:map <note>`, and run `/fastfish:map --force` if it looks stale.

## The goldfish

| Agent | Looks for |
| --- | --- |
| `design-fish` | Gaps, hidden assumptions, missing error paths, simpler alternatives, unclear writing |
| `code-fish` | Bugs, references to code that does not exist, missed reuse, untested behaviour |
| `rules-fish` | Violations of the project's skills, CLAUDE.md/AGENTS.md, Cursor/Copilot/Windsurf rules, architecture docs and ADRs. Every finding must quote the rule. |

All three are read-only (`Read`, `Grep`, `Glob`) and run on `sonnet` for speed. Change `model:` in `agents/*.md` to `opus` or `inherit` for heavier reviews.

## How the project map works

`scripts/project_map.py map` scans the repo with `git ls-files` (or a directory walk with common build folders skipped) and writes `.fastfish/project-map.md`:

- the stack, frameworks and commands (from `package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`, `Makefile`, ...)
- the layout (folders with file counts), entry points and test locations
- every **project guide**, with its scope and description

The map is cached by a fingerprint of the file list and guide timestamps. Editing code reuses the cache; adding files or editing a guide rebuilds it. `.fastfish/` is added to `.git/info/exclude` so it never shows up in `git status`.

`scripts/project_map.py scope [targets]` lists the files to review and the guides that apply to them:

| Guide | Applies when |
| --- | --- |
| `.claude/skills/*/SKILL.md`, `.agents/skills/*/SKILL.md` | always, or when a changed file matches its `paths:`/`globs:` frontmatter |
| Root `CLAUDE.md`, `AGENTS.md`, `GEMINI.md` | always |
| Nested `CLAUDE.md` / `AGENTS.md` | a changed file is inside that folder |
| `.cursor/rules/*.mdc` | `globs:`, or always when `alwaysApply: true` or no globs |
| `.github/copilot-instructions.md`, `*.instructions.md` | always, or by `applyTo:` |
| `ARCHITECTURE.md`, `CONTRIBUTING.md`, `docs/**/architecture*`, ADRs | always |

To make the rules checker sharper for one area, give the skill a scope:

```markdown
---
name: backend-architecture
description: Layering rules for the API - controllers, services, repositories.
paths: ["src/api/**", "src/services/**"]
---
Controllers never call repositories directly; go through a service. ...
```

## Layout

```
.claude-plugin/   plugin.json, marketplace.json
agents/           design-fish.md, code-fish.md, rules-fish.md
skills/           review/, check/, map/
scripts/          project_map.py
```
