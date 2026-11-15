#!/usr/bin/env bash
# Clean tinyshop, committed; then the edits below stay uncommitted.
source "$(dirname "$0")/../lib/setup.sh"

python3 - <<'EOF'
p = "src/services/cartService.ts"
s = open(p).read()
s = s.replace('import * as repo from "../repo/db.js";', 'import * as repo from "../repo/db.js";\nimport { percentOf } from "../lib/money.js";')
s += '\n/** Members get 10% off. */\nexport function memberDiscountCents(userId: string): number {\n  return percentOf(cartTotalCents(userId), 10);\n}\n'
open(p, "w").write(s)
EOF
commit_base "member discount"
cat > src/lib/money.ts <<'EOF'
export function formatCents(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

/** Returns `fraction` of an amount in cents, rounded to whole cents (0.25 = a quarter). */
export function percentOf(cents: number, fraction: number): number {
  return Math.round(cents * fraction);
}
EOF
