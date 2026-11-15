#!/usr/bin/env bash
# Clean tinyshop, committed; then the edits below stay uncommitted.
source "$(dirname "$0")/../lib/setup.sh"

cat > src/services/cartService.ts <<'EOF'
import * as repo from "../repo/db.js";

export type CartResult = { ok: true } | { ok: false; error: string };

// Totals are recomputed on every page view; cache them per user.
const totalCache = new Map<string, number>();

export function addToCart(userId: string, productId: string, quantity: number): CartResult {
  if (!Number.isInteger(quantity) || quantity < 1 || quantity > 10) {
    return { ok: false, error: "Quantity must be between 1 and 10." };
  }
  if (!repo.findProduct(productId)) return { ok: false, error: "Unknown product." };
  const cart = repo.getCart(userId);
  cart.set(productId, (cart.get(productId) ?? 0) + quantity);
  totalCache.delete(userId);
  return { ok: true };
}

export function cartTotalCents(userId: string): number {
  const cached = totalCache.get(userId);
  if (cached !== undefined) return cached;
  let total = 0;
  for (const [productId, quantity] of repo.getCart(userId)) {
    const product = repo.findProduct(productId);
    if (product) total += product.priceCents * quantity;
  }
  totalCache.set(userId, total);
  return total;
}
EOF
