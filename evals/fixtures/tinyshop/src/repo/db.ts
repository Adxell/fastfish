export type Product = { id: string; name: string; priceCents: number; stock: number };
export type OrderLine = { productId: string; quantity: number; unitPriceCents: number };
export type Order = { id: string; userId: string; lines: OrderLine[]; totalCents: number };

const products = new Map<string, Product>([
  ["p1", { id: "p1", name: "Mug", priceCents: 1200, stock: 10 }],
  ["p2", { id: "p2", name: "Lamp", priceCents: 4500, stock: 3 }],
]);
const orders = new Map<string, Order>();
const carts = new Map<string, Map<string, number>>();

export function findProduct(id: string): Product | undefined {
  return products.get(id);
}

/** Atomically checks and decrements stock. Returns false if there is not enough. */
export function reserveStock(id: string, quantity: number): boolean {
  const product = products.get(id);
  if (!product || product.stock < quantity) return false;
  product.stock -= quantity;
  return true;
}

export function getCart(userId: string): Map<string, number> {
  let cart = carts.get(userId);
  if (!cart) {
    cart = new Map();
    carts.set(userId, cart);
  }
  return cart;
}

export function saveOrder(order: Order): void {
  orders.set(order.id, order);
}

export function findOrder(id: string): Order | undefined {
  return orders.get(id);
}

export function listOrders(): Order[] {
  return [...orders.values()];
}
