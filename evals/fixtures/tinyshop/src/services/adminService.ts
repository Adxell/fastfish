import * as repo from "../repo/db.js";

export function allOrders(): repo.Order[] {
  return repo.listOrders();
}
