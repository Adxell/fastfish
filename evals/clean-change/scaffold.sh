#!/usr/bin/env bash
# Clean tinyshop, committed; then the edits below stay uncommitted.
source "$(dirname "$0")/../lib/setup.sh"

cat >> src/services/cartService.ts <<'EOF'

export function cartItemCount(userId: string): number {
  let count = 0;
  for (const quantity of repo.getCart(userId).values()) count += quantity;
  return count;
}
EOF
python3 - <<'EOF'
p = "src/routes/cart.ts"
s = open(p).read()
s = s.replace('import { addToCart, cartTotalCents } from "../services/cartService.js";',
              'import { addToCart, cartItemCount, cartTotalCents } from "../services/cartService.js";')
s += '\ncartRouter.get("/cart/count", (req, res) => {\n  res.json({ count: cartItemCount(req.userId) });\n});\n'
open(p, "w").write(s)
EOF
