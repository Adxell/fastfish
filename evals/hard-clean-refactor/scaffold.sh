#!/usr/bin/env bash
# Clean tinyshop, committed; then the edits below stay uncommitted.
source "$(dirname "$0")/../lib/setup.sh"

cat > src/services/orderService.ts <<'EOF'
import { randomUUID } from "node:crypto";
import * as repo from "../repo/db.js";

export type PlaceOrderResult = { ok: true; order: repo.Order } | { ok: false; error: string };

type LinesResult = { ok: true; lines: repo.OrderLine[] } | { ok: false; error: string };

function reserveLines(cart: Map<string, number>): LinesResult {
  const lines: repo.OrderLine[] = [];
  for (const [productId, quantity] of cart) {
    const product = repo.findProduct(productId);
    if (!product || !repo.reserveStock(productId, quantity)) {
      return { ok: false, error: `Not enough stock for ${productId}.` };
    }
    lines.push({ productId, quantity, unitPriceCents: product.priceCents });
  }
  return { ok: true, lines };
}

function totalOf(lines: readonly repo.OrderLine[]): number {
  return lines.reduce((sum, line) => sum + line.unitPriceCents * line.quantity, 0);
}

export function placeOrder(userId: string): PlaceOrderResult {
  const cart = repo.getCart(userId);
  if (cart.size === 0) return { ok: false, error: "Your cart is empty." };

  const reserved = reserveLines(cart);
  if (!reserved.ok) return reserved;

  const order: repo.Order = { id: randomUUID(), userId, lines: reserved.lines, totalCents: totalOf(reserved.lines) };
  repo.saveOrder(order);
  cart.clear();
  return { ok: true, order };
}

export function getOrder(userId: string, orderId: string): repo.Order | undefined {
  const order = repo.findOrder(orderId);
  return order && order.userId === userId ? order : undefined;
}
EOF
