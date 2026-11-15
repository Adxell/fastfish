# tinyshop

Small Express + TypeScript shop API.

## Rules

- Money is always an integer number of **cents** (`priceCents`, `totalCents`). Never use floats or dollars for money. Format only with `formatCents` from `src/lib/money.ts`.
- Architecture rules live in `.claude/skills/architecture/SKILL.md`.
- Named exports only.
