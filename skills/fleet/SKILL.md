---
name: fleet
description: Control fastfish agents running on the user's Kubernetes server - start agents on tasks or reviews, list them, read their progress, send messages to interactive ones, collect results, stop or clean them up. Use when the user asks to dispatch work to their agents/fleet/cluster/server, or asks how their remote agents are doing.
argument-hint: "[what to do, e.g. 'start 3 agents for issues 12 14 15' or 'status']"
allowed-tools: Bash(python3:*), Read
---

# fastfish fleet

Request: `$ARGUMENTS`

All actions go through the `ff` CLI, run as:

```
python3 "${CLAUDE_PLUGIN_ROOT}/fleet/ff" <command> ...
```

## Current agents (precomputed)

!`python3 "${CLAUDE_PLUGIN_ROOT}/fleet/ff" ls 2>&1 | head -40`

If that block shows an error about kubectl or the cluster, tell the user the cluster is not reachable from this machine, show the error, and point them to `fleet/README.md` (connected to fastnet — `tailscale status`? kubeconfig context? `ff setup` done?). Stop.

## Mapping requests to commands

| The user wants | Command |
| --- | --- |
| Start work on a task | `ff run "<task>" --repo <url> [--pr] [--name <short-name>]` |
| Several tasks at once | one `ff run` per task, each with its own `--name` |
| Review a branch / paths | `ff review <url> --branch <b>` or `--target <paths>` |
| Status | the table above, or `ff ls` again |
| What an agent is doing / did | `ff logs <name>` (no `-f`: it would block) and summarise the last part |
| Results | `ff out <name>`, then read `ff-out/<name>/review.md` or `status.json` |
| Tell an interactive agent something | `ff send <name> "<text>"` |
| Stop / clean up | `ff stop <name>`, `ff rm --all-done` |

Rules:
- If no repo is given and `FF_REPO` is unset, use the `origin` URL of the current project (`git remote get-url origin`) and say so.
- Write each task prompt so it stands alone: the agent sees only the prompt and the repo, not this conversation. Include the acceptance criteria and the test command if known.
- `ff attach` and `ff chat` need a real terminal. Tell the user to run them with the `!` prefix, for example `! python3 "${CLAUDE_PLUGIN_ROOT}/fleet/ff" attach <name>`, or in their own shell.
- Ask before `stop` or `rm` of agents that are still running.
- Never print, echo or ask for token values in chat. Secrets are set only by the user running `ff setup` in their own terminal.

Reply with what you started or found: agent names, status, branches/PRs, and the next command the user can run.
