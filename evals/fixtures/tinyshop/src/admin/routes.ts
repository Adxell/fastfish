import { Router } from "express";
import { requireAdmin } from "./auth.js";
import { allOrders } from "../services/adminService.js";

export const adminRouter = Router();

adminRouter.get("/admin/orders", (req, res) => {
  requireAdmin(req);
  res.json(allOrders());
});
