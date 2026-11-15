#!/usr/bin/env bash
# Clean tinyshop, committed; then the edits below stay uncommitted.
source "$(dirname "$0")/../lib/setup.sh"

python3 - <<'EOF'
p = "src/services/orderService.ts"
s = open(p).read()
s = s.replace("  return order && order.userId === userId ? order : undefined;", "  // userId kept for logging later\n  return order;")
open(p, "w").write(s)
EOF
