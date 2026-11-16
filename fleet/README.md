# fastfish fleet

Run many Claude Code agents on your own server under Kubernetes, and control them all from a terminal, wherever you are.

- Every agent is a Kubernetes **Job**: it clones your repo, works on its own branch `ff/<name>`, pushes it and, if asked, opens a PR.
- Three kinds of agent: **task** (headless, `ff run`), **review** (a fastfish review, `ff review`) and **interactive** (a Claude Code session inside tmux that you can attach to and detach from, `ff chat`).
- `ff` is a small Python CLI (stdlib only) that wraps `kubectl`. It works from any machine with a kubeconfig for the cluster.
- Remote access goes over **[fastnet](https://github.com/Adxell/fastnet)**, a self-hosted, open-source private network (Headscale + the open-source Tailscale client) that runs on the same server. No outside company sits in the middle, and the Kubernetes API is never exposed publicly.

```
 laptop / other PC ──┐                    ┌───────────── your server (k3s) ─────────────┐
   ff ls, ff run …   ├── fastnet (VPN) ───┤ kube-apiserver                               │
 phone (browser) ────┘                    │   namespace fastfish-agents                  │
   web terminal → ff …                    │     Job ff-fix-login  → pod: claude -p …     │
                                          │     Job ff-review-x   → pod: /fastfish:review│
                                          │     Job ff-chat-1     → pod: tmux + claude   │
                                          └──────────┬───────────────────────────────────┘
                                                     └─ HTTPS only → Anthropic API, GitHub
```

## Before you start

You need:
- **A Linux server** (Debian 12+ / Ubuntu 22.04+) with 4+ cores and 8+ GB RAM, reachable from the internet (public IP or router port forwards). Set it up with fastnet first by following its [getting-started guide](https://github.com/Adxell/fastnet/blob/main/docs/getting-started.md).
- **Claude access**: a Claude Pro/Max plan (for `claude setup-token`) or an Anthropic API key.
- **A GitHub fine-grained token** with Contents + Pull requests read/write on the repos agents may touch.
- **On each machine you control the fleet from**: `kubectl` and `python3`. From a phone or a borrowed computer you need only a browser: use fastnet's browser terminal.

## 1. Server setup (once)

On the server (Linux, 4+ cores and 8+ GB RAM recommended):

```sh
# fastnet: your self-hosted private network (see its README for ports and options)
git clone https://github.com/Adxell/fastnet.git
sudo ./fastnet/server/install.sh --host <public IP or DNS name> --name homelab \
  --web-terminal <your domain>   # optional: 2FA browser terminal for phones and any browser
tailscale ip -4             # the server's private address, e.g. 100.64.0.1

# k3s: a small Kubernetes; the TLS names let you reach the API over fastnet
curl -sfL https://get.k3s.io | sh -s - --write-kubeconfig-mode 600 \
  --tls-san "$(tailscale ip -4)" --tls-san homelab.fastnet.internal
sudo k3s kubectl get nodes

# let your own user run kubectl and ff (k3s's kubectl reads a root-only file unless KUBECONFIG is set)
mkdir -p ~/.kube && sudo cat /etc/rancher/k3s/k3s.yaml > ~/.kube/config && chmod 600 ~/.kube/config
echo 'export KUBECONFIG=$HOME/.kube/config' >> ~/.bashrc && export KUBECONFIG=$HOME/.kube/config
kubectl get nodes
```

Then follow fastnet's "Lock down the server" section, so port 6443 (the Kubernetes API) and SSH are reachable only over fastnet.

k3s ships with a NetworkPolicy controller, so the agent network rules in `k8s/policy.yaml` are enforced.

### Build the agent image on the server

```sh
git clone https://github.com/Adxell/fastfish.git && cd fastfish
docker build -f fleet/image/Dockerfile -t fastfish-agent:latest .
docker save fastfish-agent:latest | sudo k3s ctr images import -
```

Without Docker, use `nerdctl` or push the image to a registry you control and set `FF_IMAGE=registry.example/fastfish-agent:tag`. Pin Claude Code with `--build-arg CLAUDE_CODE_VERSION=<version>` if you want reproducible images. Rebuild and re-import to upgrade.

## 2. Client setup (each machine you control the fleet from)

```sh
# 1. Join fastnet: on the server run `sudo fastnet add laptop`, then on this machine:
scp you@<server>:fastnet-invites/laptop.sh . && sudo bash laptop.sh

# 2. Copy the kubeconfig from the server and point it at the server's fastnet address
mkdir -p ~/.kube
SERVER=100.64.0.1   # `tailscale ip -4` on the server
ssh "$SERVER" sudo cat /etc/rancher/k3s/k3s.yaml | sed "s/127.0.0.1/$SERVER/" > ~/.kube/config
chmod 600 ~/.kube/config
kubectl get nodes

# 3. Put ff on your PATH
ln -s "$PWD/fleet/ff" ~/.local/bin/ff
```

Then, once from any client:

```sh
ff setup
```

It creates the namespace, the agent service account, the quota and the network policy, then asks for:

| Secret | Value | Needed for |
| --- | --- | --- |
| `CLAUDE_CODE_OAUTH_TOKEN` | output of `claude setup-token` (uses your Pro/Max plan) | signing in, unless you use an API key |
| `ANTHROPIC_API_KEY` | an API key (pay per use) | signing in, if you have no token |
| `GH_TOKEN` | fine-grained GitHub token: Contents + Pull requests read/write on the repos agents use | private clones, pushing branches, PRs |

Values are read from the environment if set, otherwise prompted without echo, and sent to the cluster through stdin. They never appear in the Job manifest, on the command line or in logs.

### From a phone or any browser

Install fastnet with `--web-terminal <domain>` (see its README). Then open `https://<domain>:9090` on any phone or computer, sign in with your username, password and one-time code, and click **Terminal**. Nothing needs to be installed on the phone.

On the server, set up `ff` once for your user (its kubeconfig is `/etc/rancher/k3s/k3s.yaml`). Then `ff ls`, `ff logs -f …` and `ff attach …` work there as usual. Run `tmux new -A -s work` first, so your session survives a closed tab or a dropped mobile connection, and you can pick it up from your PC with `ssh` + the same command.

## 3. Using it

```sh
export FF_REPO=https://github.com/you/your-app.git     # default repo for every command

ff run "Add rate limiting to POST /login. Tests in tests/auth must pass (npm test)." --pr
ff run - --name billing-refactor < task.md            # long prompt from a file
ff review --branch feature/cart                        # fastfish review of a branch vs the default branch
ff review --target src/billing                         # review specific paths
ff chat                                                # interactive agent; Ctrl-b d to detach

ff ls                     # all agents: status, age, branch, PR, cost
ff ls -w                  # live view
ff logs -f fix-login      # readable live log (tool calls, messages, result)
ff logs --raw fix-login   # raw stream-json
ff attach chat-3f2a       # rejoin an interactive agent
ff send chat-3f2a "also update the changelog"
ff out review-cart-91c0   # saves transcript, review.md and status.json under ff-out/
ff stop fix-login         # kill a running agent
ff rm --all-done          # clean up finished agents
```

Useful flags on `run`, `review` and `chat`: `--base <branch>`, `--name`, `--model`, `--max-turns`, `--timeout 2h`, `--ttl 3d` (how long the finished Job and its logs are kept), `--cpu/--memory` (requests), `--cpu-limit/--memory-limit`, `--dry-run` (print the manifest).

Inside Claude Code you can also say things like "start agents for issues 12, 14 and 15" or "how are my agents doing?"; the `/fastfish:fleet` skill turns that into `ff` commands.

### Notifications

Set `FF_NOTIFY` before starting agents (for example `https://ntfy.sh/<a-long-random-topic>`) and each agent posts one line there when it finishes. Subscribe to the topic in the ntfy app on your phone. Anyone who knows the topic can read it, so use a long random name or your own ntfy server.

## How it works

| Piece | File |
| --- | --- |
| CLI | `ff`, `fflib/cli.py` |
| Job manifests (pure functions, unit tested) | `fflib/manifests.py` |
| Log rendering | `fflib/render.py` |
| Pod entrypoint | `image/agent-run.sh` |
| Image | `image/Dockerfile` |
| Cluster policy | `k8s/serviceaccount.yaml`, `k8s/policy.yaml` |

An agent pod:

1. Clones `REPO`, checks out the base branch and creates `ff/<name>`. The GitHub token is supplied through a git credential helper that reads the environment, so it is never written into `.git/config`.
2. Runs `claude -p "<prompt>" --output-format stream-json --permission-mode bypassPermissions --plugin-dir /opt/fastfish`. The output goes to the pod log, which is what `ff logs` reads.
3. For a review, puts the branch's changes on top of the base as uncommitted changes, which is the default scope of `/fastfish:review`, then prints the report between markers so `ff out` can extract it.
4. Commits whatever is left, pushes the branch, opens a PR with `gh` if `--pr` was given, and writes a short status (exit code, branch, PR, turns, cost) to the termination log, where `ff ls` reads it.

### Safety

Agents skip permission prompts because nobody is there to answer them. The pod is the sandbox instead:

- runs as a non-root user with all capabilities dropped and no privilege escalation;
- has no Kubernetes API token (`automountServiceAccountToken: false`, and the service account has no roles);
- can reach only DNS and HTTPS on the public internet: no cluster services, no LAN, no fastnet devices;
- is limited by CPU/memory limits, a namespace quota (8 pods by default) and a timeout;
- works on its own branch; it never pushes to the base branch unless the token allows it and the prompt asks for it, so protect your main branch on GitHub.

The agent can still read its own secrets (it needs them) and use the internet over HTTPS. Give the GitHub token access only to the repos agents should touch.

Interactive agents run with `acceptEdits`: they edit files freely but ask before running commands, and you answer when attached.

## Limits and troubleshooting

- **Logs are the record.** kubelet rotates container logs at about 10 MB, so a very long run can lose its start. `ff out` early if you need the full transcript. Logs disappear when the Job's TTL expires (`--ttl`).
- **`ImagePullBackOff`** in `ff ls`: the image is not on the node. Re-run the `docker save | k3s ctr images import` step, or set `FF_IMAGE` to a registry image.
- **`CreateContainerConfigError`** or the agent exits with "no Claude credentials": run `ff setup` again.
- **Clone or push fails**: the repo is private or the token lacks write access. Check `GH_TOKEN`.
- **Git server on your LAN**: add an egress rule for its address in `k8s/policy.yaml`; private ranges are blocked by default.
- **Plan limits**: with a subscription token, all agents share your plan's usage limits. Start fewer at once or use an API key.
- **Different namespace or cluster**: set `FF_NAMESPACE` / `FF_CONTEXT`.

## Tests

```sh
python3 -m unittest discover fleet/tests
```
