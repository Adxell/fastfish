import { randomUUID } from "node:crypto";
import * as repo from "../repo/db.js";

export type PlaceOrderResult = { ok: true; order: repo.Order } | { ok: false; error: string };

export function placeOrder(userId: string): PlaceOrderResult {
  const cart = repo.getCart(userId);
  if (cart.size === 0) return { ok: false, error: "Your cart is empty." };

  const lines: repo.OrderLine[] = [];
  for (const [productId, quantity] of cart) {
    const product = repo.findProduct(productId);
    if (!product || !repo.reserveStock(productId, quantity)) {
      return { ok: false, error: `Not enough stock for ${productId}.` };
    }
    lines.push({ productId, quantity, unitPriceCents: product.priceCents });
  }

  const totalCents = lines.reduce((sum, l) => sum + l.unitPriceCents * l.quantity, 0);
  const order: repo.Order = { id: randomUUID(), userId, lines, totalCents };
  repo.saveOrder(order);
  cart.clear();
  return { ok: true, order };
}

export function getOrder(userId: string, orderId: string): repo.Order | undefined {
  const order = repo.findOrder(orderId);
  return order && order.userId === userId ? order : undefined;
}
