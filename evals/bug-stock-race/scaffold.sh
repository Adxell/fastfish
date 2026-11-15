#!/usr/bin/env bash
# Clean tinyshop, committed; then the edits below stay uncommitted.
source "$(dirname "$0")/../lib/setup.sh"

python3 - <<'EOF'
p = "src/services/orderService.ts"
s = open(p).read()
s = s.replace(
"    if (!product || !repo.reserveStock(productId, quantity)) {\n      return { ok: false, error: `Not enough stock for ${productId}.` };\n    }\n",
"    if (!product || product.stock < quantity) {\n      return { ok: false, error: `Not enough stock for ${productId}.` };\n    }\n    product.stock = product.stock - quantity;\n")
open(p, "w").write(s)
EOF
