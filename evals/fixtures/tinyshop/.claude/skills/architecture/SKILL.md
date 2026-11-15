---
name: architecture
description: Layering rules for tinyshop - routes, services, repo. Use when adding or reviewing any code under src/.
paths: ["src/**"]
---

# Architecture

`src/routes` → `src/services` → `src/repo`

- Routes parse the request, call **one service function**, and send the response. Routes never import from `src/repo` and contain no business rules.
- Services hold the business rules. They never import `express`.
- Only `src/repo` touches the data store.
- Every service function that reads or changes a user's data takes the `userId` and must check that the data belongs to that user. Return `undefined` (not found) otherwise.
- Stock changes go through `repo.reserveStock`, which checks and decrements atomically. Never read stock and write it back in two steps.
