#!/usr/bin/env bash
# Clean tinyshop, committed; then the edits below stay uncommitted.
source "$(dirname "$0")/../lib/setup.sh"

cat > src/routes/orders.ts <<'EOF'
import { Router } from "express";
import { getOrder, placeOrder } from "../services/orderService.js";

export const ordersRouter = Router();

ordersRouter.post("/orders", (req, res) => {
  const result = placeOrder(req.userId);
  if (!result.ok) return res.status(409).json({ error: result.error });
  res.status(201).json(result.order);
});

ordersRouter.get("/orders/:id", (req, res) => {
  // Support staff look up a customer's order by passing ?userId=<customer>.
  const userId = typeof req.query.userId === "string" ? req.query.userId : req.userId;
  const order = getOrder(userId, req.params.id);
  if (!order) return res.status(404).json({ error: "Not found" });
  res.json(order);
});
EOF
