#!/usr/bin/env bash
# Clean tinyshop, committed; then the edits below stay uncommitted.
source "$(dirname "$0")/../lib/setup.sh"

mkdir -p .claude/skills/service-conventions
cat > .claude/skills/service-conventions/SKILL.md <<'EOF'
---
name: service-conventions
description: Coding conventions for tinyshop service functions (src/services).
paths: ["src/services/**"]
---

# Service conventions

1. Service functions are plain functions; no classes.
2. Prefer early returns over nested if/else.
3. Use `Map` for in-memory lookups, not plain objects.
4. Name boolean variables with is/has/can prefixes.
5. Keep functions under 40 lines; extract helpers otherwise.
6. Validate inputs at the top of each service function.
7. Return typed results (`{ ok: true } | { ok: false; error }`) for expected failures.
8. Throw only for programmer errors.
9. Do not log from services; routes log.
10. Avoid default parameters on exported functions.
11. Sort lists deterministically before returning them.
12. Use `readonly` arrays in return types where callers should not mutate.
13. Timestamps: services never call `Date.now()` or `new Date()`. Take the time from `now()` in `src/lib/clock.ts`, so tests can freeze it, and store it as an ISO string.
14. IDs come from `randomUUID()` in services, never from the client.
15. Keep string literals for user-facing errors short and end them with a period.
16. Never mutate function arguments.
17. Prefer `for...of` over `forEach`.
18. Don't export helper functions only used in one file.
19. Use `const` unless reassigned.
20. Group imports: node built-ins, packages, then local.
EOF
cat > src/lib/clock.ts <<'EOF'
let frozen: string | undefined;
export function now(): string {
  return frozen ?? new Date().toISOString();
}
export function freezeClock(iso: string | undefined): void {
  frozen = iso;
}
EOF
commit_base "service conventions"

python3 - <<'EOF'
p = "src/repo/db.ts"
s = open(p).read()
s = s.replace("export type Order = { id: string; userId: string; lines: OrderLine[]; totalCents: number };",
              "export type Order = { id: string; userId: string; lines: OrderLine[]; totalCents: number; createdAt: string };")
open(p, "w").write(s)
p = "src/services/orderService.ts"
s = open(p).read()
s = s.replace("const order: repo.Order = { id: randomUUID(), userId, lines, totalCents };",
              "const order: repo.Order = { id: randomUUID(), userId, lines, totalCents, createdAt: new Date().toISOString() };")
open(p, "w").write(s)
EOF
