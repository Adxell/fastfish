# Admin area

Every admin route handler must call `requireAdmin(req)` from `./auth.ts` as its first line, before reading any data. No exceptions, including read-only routes.
