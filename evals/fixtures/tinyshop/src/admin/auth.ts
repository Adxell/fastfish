import type { Request } from "express";

export class ForbiddenError extends Error {}

export function requireAdmin(req: Request): void {
  if (req.role !== "admin") throw new ForbiddenError("Admins only");
}
