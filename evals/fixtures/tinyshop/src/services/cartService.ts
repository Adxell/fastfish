import * as repo from "../repo/db.js";

export type CartResult = { ok: true } | { ok: false; error: string };

export function addToCart(userId: string, productId: string, quantity: number): CartResult {
  if (!Number.isInteger(quantity) || quantity < 1 || quantity > 10) {
    return { ok: false, error: "Quantity must be between 1 and 10." };
  }
  if (!repo.findProduct(productId)) return { ok: false, error: "Unknown product." };
  const cart = repo.getCart(userId);
  cart.set(productId, (cart.get(productId) ?? 0) + quantity);
  return { ok: true };
}

export function cartTotalCents(userId: string): number {
  let total = 0;
  for (const [productId, quantity] of repo.getCart(userId)) {
    const product = repo.findProduct(productId);
    if (product) total += product.priceCents * quantity;
  }
  return total;
}
