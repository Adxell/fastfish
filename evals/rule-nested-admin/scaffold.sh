#!/usr/bin/env bash
# Clean tinyshop, committed; then the edits below stay uncommitted.
source "$(dirname "$0")/../lib/setup.sh"

cat > src/admin/routes.ts <<'EOF'
import { Router } from "express";
import { requireAdmin } from "./auth.js";
import { allOrders } from "../services/adminService.js";

export const adminRouter = Router();

adminRouter.get("/admin/orders", (req, res) => {
  requireAdmin(req);
  res.json(allOrders());
});

adminRouter.get("/admin/orders/count", (req, res) => {
  res.json({ count: allOrders().length });
});
EOF
