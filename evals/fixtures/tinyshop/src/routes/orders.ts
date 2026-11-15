import { Router } from "express";
import { getOrder, placeOrder } from "../services/orderService.js";

export const ordersRouter = Router();

ordersRouter.post("/orders", (req, res) => {
  const result = placeOrder(req.userId);
  if (!result.ok) return res.status(409).json({ error: result.error });
  res.status(201).json(result.order);
});

ordersRouter.get("/orders/:id", (req, res) => {
  const order = getOrder(req.userId, req.params.id);
  if (!order) return res.status(404).json({ error: "Not found" });
  res.json(order);
});
