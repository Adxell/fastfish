import { Router } from "express";
import { addToCart, cartTotalCents } from "../services/cartService.js";
import { formatCents } from "../lib/money.js";

export const cartRouter = Router();

cartRouter.post("/cart", (req, res) => {
  const result = addToCart(req.userId, String(req.body.productId), Number(req.body.quantity));
  if (!result.ok) return res.status(422).json({ error: result.error });
  res.json({ ok: true });
});

cartRouter.get("/cart/total", (req, res) => {
  const cents = cartTotalCents(req.userId);
  res.json({ totalCents: cents, display: formatCents(cents) });
});
