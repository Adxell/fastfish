#!/usr/bin/env python3
"""Build a cached project map and review scope for fastfish goldfish reviewers.

Stdlib only. Two commands:

  project_map.py map   [--root DIR] [--force]   -> writes .fastfish/project-map.md (cached)
  project_map.py scope [--root DIR] [TARGET...] -> prints the review scope (files + guides that apply)

The map is keyed by a fingerprint of the file list (not file contents), so editing
code does not invalidate it; adding/removing files or editing a guide does.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

OUT_DIR = ".fastfish"
MAP_FILE = "project-map.md"
NOTES_FILE = "notes.md"
MAX_FILES = 50_000
MAX_SCOPE_FILES = 200

SKIP_DIRS = {
    ".git", "node_modules", "dist", "build", "out", ".next", ".nuxt", ".venv", "venv",
    "env", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache", "target",
    "vendor", "coverage", ".turbo", ".gradle", ".idea", ".cache", OUT_DIR,
}

LANG_BY_EXT = {
    ".py": "Python", ".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript",
    ".jsx": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript", ".go": "Go",
    ".rs": "Rust", ".java": "Java", ".kt": "Kotlin", ".swift": "Swift", ".rb": "Ruby",
    ".php": "PHP", ".cs": "C#", ".c": "C", ".h": "C", ".cpp": "C++", ".hpp": "C++",
    ".dart": "Dart", ".scala": "Scala", ".ex": "Elixir", ".exs": "Elixir",
    ".vue": "Vue", ".svelte": "Svelte", ".sql": "SQL", ".sh": "Shell",
    ".css": "CSS", ".scss": "CSS", ".html": "HTML", ".md": "Markdown",
}

MANIFESTS = {
    "package.json": "Node.js", "pyproject.toml": "Python", "requirements.txt": "Python",
    "setup.py": "Python", "Pipfile": "Python", "go.mod": "Go", "Cargo.toml": "Rust",
    "pom.xml": "Java (Maven)", "build.gradle": "JVM (Gradle)", "build.gradle.kts": "JVM (Gradle)",
    "Gemfile": "Ruby", "composer.json": "PHP", "pubspec.yaml": "Dart/Flutter",
    "mix.exs": "Elixir", "Package.swift": "Swift", "deno.json": "Deno",
    "Dockerfile": "Docker", "docker-compose.yml": "Docker Compose",
    "compose.yaml": "Docker Compose", "Makefile": "Make",
}

FRAMEWORK_HINTS = {
    "next": "Next.js", "react": "React", "vue": "Vue", "nuxt": "Nuxt", "@angular/core": "Angular",
    "svelte": "Svelte", "@sveltejs/kit": "SvelteKit", "express": "Express", "@nestjs/core": "NestJS",
    "fastify": "Fastify", "hono": "Hono", "astro": "Astro", "electron": "Electron",
    "react-native": "React Native", "expo": "Expo", "prisma": "Prisma", "typeorm": "TypeORM",
    "drizzle-orm": "Drizzle", "vitest": "Vitest", "jest": "Jest", "@playwright/test": "Playwright",
    "tailwindcss": "Tailwind", "django": "Django", "fastapi": "FastAPI", "flask": "Flask",
    "sqlalchemy": "SQLAlchemy", "pydantic": "Pydantic", "pytest": "pytest",
}

ENTRY_NAMES = {
    "main.py", "__main__.py", "app.py", "manage.py", "wsgi.py", "asgi.py", "main.go",
    "main.rs", "lib.rs", "index.ts", "index.js", "main.ts", "main.js", "server.ts",
    "server.js", "app.ts", "app.js", "main.tsx", "index.tsx", "App.tsx", "Program.cs",
    "Application.java", "main.dart",
}

LINT_CONFIGS = {
    ".editorconfig", ".eslintrc", ".eslintrc.js", ".eslintrc.json", ".eslintrc.cjs",
    "eslint.config.js", "eslint.config.mjs", ".prettierrc", ".prettierrc.json",
    "prettier.config.js", "biome.json", "ruff.toml", ".ruff.toml", "tsconfig.json",
    ".golangci.yml", ".golangci.yaml", "rustfmt.toml", ".rubocop.yml", "setup.cfg",
    ".flake8", "mypy.ini", ".stylelintrc",
}


# ---------------------------------------------------------------- helpers


def run(cmd: list[str], cwd: Path) -> str | None:
    try:
        res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return res.stdout if res.returncode == 0 else None


def is_git(root: Path) -> bool:
    return run(["git", "rev-parse", "--is-inside-work-tree"], root) is not None


def list_files(root: Path) -> list[str]:
    if is_git(root):
        out = run(["git", "ls-files", "-co", "--exclude-standard"], root)
        if out is not None:
            files = [f for f in out.splitlines() if f and not f.startswith(OUT_DIR + "/")]
            return sorted(f for f in files if (root / f).is_file())[:MAX_FILES]
    files: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        rel = Path(dirpath).relative_to(root)
        for name in sorted(filenames):
            files.append((rel / name).as_posix() if str(rel) != "." else name)
            if len(files) >= MAX_FILES:
                return files
    return files


def read_text(path: Path, limit: int = 200_000) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            return fh.read(limit)
    except OSError:
        return ""


def parse_frontmatter(text: str) -> dict[str, object]:
    """Tiny YAML-frontmatter reader: scalars, folded/literal blocks and string lists."""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    data: dict[str, object] = {}
    key: str | None = None
    mode = ""  # "block" for >- / |, "list" for "- item" lines
    for line in text[3:end].splitlines():
        if not line.strip():
            continue
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if m and not line.startswith((" ", "\t")):
            key, val = m.group(1), m.group(2).strip()
            if val in (">", ">-", "|", "|-", ">+", "|+"):
                data[key], mode = "", "block"
            elif val == "":
                data[key], mode = [], "list"
            elif val.startswith("[") and val.endswith("]"):
                data[key] = [v.strip().strip("'\"") for v in val[1:-1].split(",") if v.strip()]
                mode = ""
            else:
                data[key], mode = val.strip("'\""), ""
        elif key and mode == "list" and line.strip().startswith("- "):
            data[key].append(line.strip()[2:].strip().strip("'\""))  # type: ignore[union-attr]
        elif key and mode == "block":
            data[key] = (str(data[key]) + " " + line.strip()).strip()
    return data


def first_line_summary(text: str) -> str:
    body = text
    if body.startswith("---"):
        end = body.find("\n---", 3)
        body = body[end + 4:] if end != -1 else body
    heading = ""
    for raw in body.splitlines():
        line = raw.strip().lstrip("#").strip()
        if not line or line.startswith(("<", "!", "[![", "```")):
            continue
        if raw.lstrip().startswith("#"):
            heading = heading or line
            continue
        return (f"{heading}: {line}" if heading else line)[:160]
    return heading[:160]


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    pattern = pattern.strip().lstrip("./")
    if pattern.startswith("/"):
        pattern = pattern[1:]
    out, i = "", 0
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
            continue
        if pattern.startswith("**", i):
            out += ".*"
            i += 2
            continue
        if c == "*":
            out += "[^/]*"
        elif c == "?":
            out += "[^/]"
        elif c == "{":
            close = pattern.find("}", i)
            if close != -1:
                out += "(?:" + "|".join(re.escape(p) for p in pattern[i + 1:close].split(",")) + ")"
                i = close + 1
                continue
            out += re.escape(c)
        else:
            out += re.escape(c)
        i += 1
    if "/" not in pattern:
        out = "(?:.*/)?" + out
    return re.compile("^" + out + "(?:/.*)?$")


def as_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [v.strip() for v in value.split(",") if v.strip()]
    return []


# ---------------------------------------------------------------- guides


def guide_kind(path: str) -> str | None:
    p = path.lower()
    name = p.rsplit("/", 1)[-1]
    if re.search(r"(^|/)\.claude/skills/[^/]+/skill\.md$", p) or re.search(r"(^|/)\.agents/skills/[^/]+/skill\.md$", p):
        return "skill"
    if re.search(r"(^|/)\.claude/agents/[^/]+\.md$", p):
        return "agent"
    if re.search(r"(^|/)\.claude/commands/.+\.md$", p):
        return "command"
    if name in ("claude.md", "claude.local.md"):
        return "claude-md"
    if name in ("agents.md", "gemini.md"):
        return "agents-md"
    if p.startswith(".cursor/rules/") or name == ".cursorrules":
        return "cursor-rule"
    if p.startswith(".windsurf/rules/") or name == ".windsurfrules":
        return "windsurf-rule"
    if p == ".github/copilot-instructions.md" or p.endswith(".instructions.md"):
        return "copilot-rule"
    if re.search(r"(^|/)(adr|adrs|decisions)/.+\.md$", p):
        return "adr"
    if name in ("architecture.md", "design.md", "conventions.md", "style.md", "styleguide.md",
                "coding-standards.md", "code_style.md", "contributing.md"):
        return "architecture-doc" if name != "contributing.md" else "contributing"
    if re.search(r"(^|/)docs?/.*(architecture|convention|style|standard|guideline).*\.md$", p):
        return "architecture-doc"
    if name in LINT_CONFIGS and "/" not in p:
        return "lint-config"
    return None


def collect_guides(root: Path, files: list[str]) -> list[dict[str, object]]:
    guides = []
    for f in files:
        kind = guide_kind(f)
        if not kind:
            continue
        entry: dict[str, object] = {"path": f, "kind": kind, "scope": [], "description": ""}
        if kind != "lint-config":
            text = read_text(root / f, 20_000)
            fm = parse_frontmatter(text)
            entry["description"] = str(fm.get("description", "")).strip()[:300] or first_line_summary(text)
            scope = as_list(fm.get("paths")) or as_list(fm.get("globs")) or as_list(fm.get("applyTo"))
            if fm.get("alwaysApply") in ("true", True):
                scope = []
            # Nested CLAUDE.md / AGENTS.md apply to their own directory.
            if kind in ("claude-md", "agents-md") and "/" in f:
                scope = [f.rsplit("/", 1)[0] + "/**"]
            entry["scope"] = scope
        guides.append(entry)
    order = ["claude-md", "agents-md", "skill", "architecture-doc", "adr", "cursor-rule",
             "copilot-rule", "windsurf-rule", "contributing", "agent", "command", "lint-config"]
    guides.sort(key=lambda g: (order.index(str(g["kind"])), str(g["path"])))
    return guides


def guide_applies(guide: dict[str, object], scoped: list[str]) -> bool:
    if guide["kind"] in ("agent", "command", "lint-config"):
        return False
    scope = guide["scope"]
    if not scope:
        return True
    regexes = [glob_to_regex(p) for p in scope]  # type: ignore[union-attr]
    return any(r.match(f) for r in regexes for f in scoped)


# ---------------------------------------------------------------- stack


def detect_stack(root: Path, files: list[str]) -> dict[str, list[str]]:
    top = {f for f in files if "/" not in f}
    stack = sorted({lang for m, lang in MANIFESTS.items() if m in top})
    frameworks: set[str] = set()
    commands: list[str] = []

    if "package.json" in top:
        try:
            pkg = json.loads(read_text(root / "package.json"))
        except json.JSONDecodeError:
            pkg = {}
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        frameworks |= {v for k, v in FRAMEWORK_HINTS.items() if k in deps}
        if "typescript" in deps:
            frameworks.add("TypeScript")
        pm = "pnpm" if "pnpm-lock.yaml" in top else "yarn" if "yarn.lock" in top else "bun" if "bun.lockb" in top or "bun.lock" in top else "npm"
        for name, cmd in pkg.get("scripts", {}).items():
            if name in ("dev", "start", "build", "test", "lint", "typecheck", "format", "check", "e2e"):
                commands.append(f"`{pm} run {name}` → {cmd}")
        if pkg.get("workspaces"):
            frameworks.add("monorepo (workspaces)")

    pyproject = read_text(root / "pyproject.toml") if "pyproject.toml" in top else ""
    reqs = read_text(root / "requirements.txt") if "requirements.txt" in top else ""
    pytext = (pyproject + "\n" + reqs).lower()
    for k, v in FRAMEWORK_HINTS.items():
        if re.search(rf"(^|[\s\"'\[]){re.escape(k)}([\s\"'=<>~\[,]|$)", pytext, re.M):
            frameworks.add(v)
    if pytext.strip():
        if "pytest" in pytext or any(f.startswith("tests/") for f in files):
            commands.append("`pytest`")
        if "[tool.ruff" in pytext:
            commands.append("`ruff check .`")
        if "[tool.mypy" in pytext:
            commands.append("`mypy .`")
    if "go.mod" in top:
        mod = re.search(r"^module\s+(\S+)", read_text(root / "go.mod"), re.M)
        if mod:
            frameworks.add(f"module {mod.group(1)}")
        commands += ["`go build ./...`", "`go test ./...`"]
    if "Cargo.toml" in top:
        commands += ["`cargo build`", "`cargo test`", "`cargo clippy`"]
    if "Makefile" in top:
        targets = re.findall(r"^([A-Za-z][\w-]*):", read_text(root / "Makefile"), re.M)
        if targets:
            commands.append("`make` targets: " + ", ".join(sorted(set(targets))[:12]))
    return {"stack": stack, "frameworks": sorted(frameworks), "commands": commands}


def layout_tree(files: list[str], depth: int = 2, per_dir: int = 14) -> list[str]:
    counts: Counter[str] = Counter()
    for f in files:
        parts = f.split("/")[:-1]
        for d in range(1, min(len(parts), depth) + 1):
            counts["/".join(parts[:d])] += 1
    lines = []
    tops = sorted(d for d in counts if "/" not in d)
    for t in tops:
        lines.append(f"- `{t}/` ({counts[t]} files)")
        kids = sorted((d for d in counts if d.startswith(t + "/") and d.count("/") == 1),
                      key=lambda d: -counts[d])
        for k in kids[:per_dir]:
            lines.append(f"  - `{k}/` ({counts[k]})")
        if len(kids) > per_dir:
            lines.append(f"  - … {len(kids) - per_dir} more")
    root_files = [f for f in files if "/" not in f]
    if root_files:
        shown = ", ".join(f"`{f}`" for f in root_files[:25])
        lines.append(f"- root files: {shown}" + (" …" if len(root_files) > 25 else ""))
    return lines


# ---------------------------------------------------------------- map


def fingerprint(root: Path, files: list[str], guides: list[dict[str, object]]) -> str:
    h = hashlib.sha256()
    h.update("\n".join(files).encode())
    for g in guides:
        try:
            h.update(f"{g['path']}:{(root / str(g['path'])).stat().st_mtime_ns}".encode())
        except OSError:
            pass
    notes = root / OUT_DIR / NOTES_FILE
    if notes.exists():
        h.update(str(notes.stat().st_mtime_ns).encode())
    return h.hexdigest()[:16]


def ensure_excluded(root: Path) -> None:
    """Keep .fastfish/ out of git status without touching tracked files."""
    git_dir = run(["git", "rev-parse", "--git-dir"], root)
    if not git_dir:
        return
    exclude = (root / git_dir.strip() / "info" / "exclude")
    try:
        exclude.parent.mkdir(parents=True, exist_ok=True)
        current = exclude.read_text() if exclude.exists() else ""
        if f"/{OUT_DIR}/" not in current.split():
            with exclude.open("a") as fh:
                fh.write(("" if current.endswith("\n") or not current else "\n") + f"/{OUT_DIR}/\n")
    except OSError:
        pass


def render_map(root: Path, files: list[str], guides: list[dict[str, object]], fp: str) -> str:
    info = detect_stack(root, files)
    langs = Counter(LANG_BY_EXT[Path(f).suffix] for f in files if Path(f).suffix in LANG_BY_EXT)
    entries = [f for f in files if f.rsplit("/", 1)[-1] in ENTRY_NAMES and f.count("/") <= 3][:20]
    tests = sorted({f.split("/")[0] + "/" for f in files
                    if re.search(r"(^|/)(tests?|__tests__|spec|e2e)(/|$)", f)})[:10]
    test_files = sum(1 for f in files if re.search(r"(\.|_)(test|spec)\.\w+$|(^|/)test_[^/]+\.py$", f))

    out = [
        "# Project map",
        "",
        f"<!-- fastfish fingerprint: {fp} -->",
        f"Root: `{root}` · {len(files)} files · generated {dt.datetime.now().isoformat(timespec='seconds')}",
        "",
        "Read this first. It replaces exploring the repo to learn its shape. Open source files only to verify specifics.",
        "",
        "## Stack",
        "",
        f"- Detected: {', '.join(info['stack']) or 'unknown'}",
        f"- Frameworks / tools: {', '.join(info['frameworks']) or 'none detected'}",
        f"- Languages (files): {', '.join(f'{k} {v}' for k, v in langs.most_common(8)) or 'n/a'}",
    ]
    if info["commands"]:
        out += ["", "## Commands", ""] + [f"- {c}" for c in info["commands"]]
    out += ["", "## Layout", ""] + layout_tree(files)
    if entries:
        out += ["", "## Entry points", ""] + [f"- `{e}`" for e in entries]
    out += ["", "## Tests", "", f"- Test locations: {', '.join(f'`{t}`' for t in tests) or 'none found'} · {test_files} test files"]

    out += ["", "## Project guides (conventions to check against)", ""]
    if guides:
        out += ["| Guide | Kind | Applies to | What it covers |", "| --- | --- | --- | --- |"]
        for g in guides:
            scope = ", ".join(f"`{s}`" for s in g["scope"]) or "everything"  # type: ignore[union-attr]
            if g["kind"] in ("agent", "command"):
                scope = "tooling (not a rule)"
            desc = str(g["description"]).replace("|", "\\|").replace("\n", " ")
            out.append(f"| `{g['path']}` | {g['kind']} | {scope} | {desc} |")
    else:
        out.append("No project skills, CLAUDE.md, AGENTS.md, rules or architecture docs found. "
                   "Reviewers infer conventions from neighbouring code.")

    notes = read_text(root / OUT_DIR / NOTES_FILE).strip()
    if notes:
        out += ["", "## Team notes (from .fastfish/notes.md)", "", notes]
    return "\n".join(out) + "\n"


def cmd_map(root: Path, force: bool) -> int:
    files = list_files(root)
    guides = collect_guides(root, files)
    fp = fingerprint(root, files, guides)
    out_dir = root / OUT_DIR
    map_path = out_dir / MAP_FILE
    (out_dir / "reviews").mkdir(parents=True, exist_ok=True)
    ensure_excluded(root)
    if not force and map_path.exists() and f"fingerprint: {fp}" in read_text(map_path, 400):
        print(f"fastfish map: {map_path} (cached, {len(files)} files, {len(guides)} guides)")
        return 0
    map_path.write_text(render_map(root, files, guides, fp), encoding="utf-8")
    print(f"fastfish map: {map_path} (rebuilt, {len(files)} files, {len(guides)} guides)")
    return 0


# ---------------------------------------------------------------- scope


def changed_files(root: Path) -> tuple[list[str], str]:
    if not is_git(root):
        return [], "not a git repository"
    status = run(["git", "status", "--porcelain", "-uall"], root) or ""
    files = []
    for line in status.splitlines():
        path = line[3:].split(" -> ")[-1].strip().strip('"')
        if path and not path.startswith(OUT_DIR + "/") and (root / path).is_file():
            files.append(path)
    if files:
        return sorted(set(files)), "uncommitted changes"
    last = run(["git", "diff", "--name-only", "HEAD~1", "HEAD"], root) or ""
    files = [f for f in last.splitlines() if f and (root / f).is_file()]
    return files, "last commit (working tree clean)"


def cmd_scope(root: Path, targets: list[str]) -> int:
    all_files = list_files(root)
    # Arguments can be free text ("review my changes"); keep only words that are paths.
    words = [t for t in targets if not (Path.cwd() / t).exists()]
    targets = [t for t in targets if (Path.cwd() / t).exists()]
    if words:
        print(f"note: ignored arguments that are not paths: {' '.join(words)[:200]}", file=sys.stderr)
    if targets:
        scoped: list[str] = []
        for t in targets:
            p = (Path.cwd() / t).resolve()
            try:
                rel = p.relative_to(root.resolve()).as_posix()
            except ValueError:
                print(f"warning: {t} is outside the project root; skipped", file=sys.stderr)
                continue
            if p.is_dir():
                prefix = "" if rel == "." else rel + "/"
                scoped += [f for f in all_files if f.startswith(prefix)]
            elif p.is_file():
                scoped.append(rel)
        origin = "explicit target"
    else:
        scoped, origin = changed_files(root)

    guides = collect_guides(root, all_files)
    applicable = [g for g in guides if guide_applies(g, scoped)] if scoped else []
    docs = [f for f in scoped if f.endswith((".md", ".mdx", ".rst", ".txt"))]
    code = [f for f in scoped if f not in docs]

    print("## Review scope")
    print()
    print(f"- Source: {origin} · {len(scoped)} files ({len(code)} code, {len(docs)} docs)")
    if len(scoped) > MAX_SCOPE_FILES:
        print(f"- Showing first {MAX_SCOPE_FILES}; narrow the target for a sharper review.")
    for f in scoped[:MAX_SCOPE_FILES]:
        print(f"  - `{f}`")
    if not targets and is_git(root) and origin == "uncommitted changes":
        stat = run(["git", "diff", "HEAD", "--shortstat"], root)
        if stat and stat.strip():
            print(f"- Diff: {stat.strip()} (see `git diff HEAD`)")
    print()
    print("## Guides that apply to this scope")
    print()
    if applicable:
        for g in applicable:
            scope = ", ".join(g["scope"]) or "always"  # type: ignore[arg-type]
            print(f"- `{g['path']}` ({g['kind']}; {scope}) — {g['description']}")
    else:
        print("- none (infer conventions from neighbouring code)")
    print()
    print(f"TIMESTAMP={dt.datetime.now().strftime('%Y%m%d-%H%M')}")
    print(f"SCOPE_KIND={'docs' if docs and not code else 'code' if code and not docs else 'mixed' if scoped else 'empty'}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=["map", "scope"])
    parser.add_argument("targets", nargs="*")
    parser.add_argument("--root", default=os.getcwd())
    parser.add_argument("--force", action="store_true")
    args, _unknown = parser.parse_known_args()  # tolerate skill flags like --quick
    # Skills pass "$ARGUMENTS" quoted as one string (it may be free text with
    # apostrophes), so split it here and drop flags like --quick.
    args.targets = [t for arg in args.targets for t in arg.split() if not t.startswith("--")]
    root = Path(args.root).resolve()
    top = run(["git", "rev-parse", "--show-toplevel"], root)
    if top:
        root = Path(top.strip())
    if args.command == "map":
        return cmd_map(root, args.force)
    return cmd_scope(root, args.targets)


if __name__ == "__main__":
    sys.exit(main())
