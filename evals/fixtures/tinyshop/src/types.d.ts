declare namespace Express {
  interface Request {
    userId: string;
    role: "customer" | "admin";
  }
}
