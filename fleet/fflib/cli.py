"""ff: start, watch, talk to and stop Claude Code agents running as Kubernetes Jobs.

Configuration (environment):
  FF_NAMESPACE   namespace for agents          (default: fastfish-agents)
  FF_CONTEXT     kubectl context to use         (default: current context)
  FF_IMAGE       agent image                    (default: fastfish-agent:latest)
  FF_REPO        default repository URL for run/review/chat
  FF_NOTIFY      ntfy-style URL; agents POST a line there when they finish
"""
from __future__ import annotations

import argparse
import datetime as dt
import getpass
import json
import os
import sys
import time
from pathlib import Path

from . import manifests as m
from .kube import Kube, KubeError
from .render import render_lines, split_log

FLEET_DIR = Path(__file__).resolve().parent.parent
K8S_DIR = FLEET_DIR / "k8s"


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, "") or default


def kube() -> Kube:
    return Kube(env("FF_NAMESPACE", "fastfish-agents"), env("FF_CONTEXT"))


# ---------------------------------------------------------------- status helpers


def _when(ts: str) -> dt.datetime:
    return dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))


def age(ts: str | None) -> str:
    if not ts:
        return "-"
    secs = int((dt.datetime.now(dt.timezone.utc) - _when(ts)).total_seconds())
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if secs >= size:
            return f"{secs // size}{unit}"
    return f"{max(secs, 0)}s"


def termination(pod: dict | None) -> dict:
    """The status.json agent-run.sh writes to /dev/termination-log."""
    for cs in ((pod or {}).get("status") or {}).get("containerStatuses") or []:
        msg = ((cs.get("state") or {}).get("terminated") or {}).get("message")
        if msg:
            try:
                return json.loads(msg)
            except json.JSONDecodeError:
                return {"note": msg[:80]}
    return {}


def agent_status(job: dict, pod: dict | None) -> str:
    status = job.get("status") or {}
    for cond in status.get("conditions") or []:
        if cond.get("status") != "True":
            continue
        if cond.get("type") == "Failed":
            return "timeout" if cond.get("reason") == "DeadlineExceeded" else "failed"
        if cond.get("type") == "Complete":
            return "done"
    if job.get("metadata", {}).get("deletionTimestamp"):
        return "stopping"
    if pod:
        pstatus = pod.get("status") or {}
        for cs in pstatus.get("containerStatuses") or []:
            reason = ((cs.get("state") or {}).get("waiting") or {}).get("reason")
            if reason and reason != "ContainerCreating":
                return reason  # ImagePullBackOff, CreateContainerConfigError, ...
        if pstatus.get("phase") == "Pending":
            return "starting"
        if pstatus.get("phase") == "Running":
            return "running"
    return "running" if status.get("active") else "pending"


def pods_by_agent(k: Kube) -> dict[str, dict]:
    pods: dict[str, dict] = {}
    items = k.get_json(["pods", "-l", f"app={m.APP_LABEL}"]).get("items", [])
    for pod in sorted(items, key=lambda p: p["metadata"]["creationTimestamp"]):
        pods[pod["metadata"]["labels"].get("ff/name", "")] = pod
    return pods


def find_pod(k: Kube, name: str) -> dict | None:
    return pods_by_agent(k).get(name)


def wait_for_pod(k: Kube, name: str, want: str = "Running", timeout: int = 300) -> dict:
    """Wait until the agent's pod leaves Pending. Returns the pod (Running or already finished)."""
    deadline = time.time() + timeout
    shown = False
    while True:
        pod = find_pod(k, name)
        phase = ((pod or {}).get("status") or {}).get("phase")
        if pod and phase != "Pending":
            return pod
        if pod:
            for cs in pod["status"].get("containerStatuses") or []:
                waiting = (cs.get("state") or {}).get("waiting") or {}
                if waiting.get("reason") not in (None, "ContainerCreating"):
                    raise KubeError(f"agent {name} cannot start: {waiting['reason']}: {waiting.get('message', '')}")
        if time.time() > deadline:
            raise KubeError(f"agent {name} did not reach {want} within {timeout}s (check `ff ls`)")
        if not shown:
            print(f"waiting for agent {name} to start…", file=sys.stderr)
            shown = True
        time.sleep(2)


# ---------------------------------------------------------------- commands


def resolve_prompt(words: list[str]) -> str:
    if words == ["-"]:
        return sys.stdin.read().strip()
    return " ".join(words).strip()


def spec_from_args(args: argparse.Namespace, mode: str, prompt: str) -> m.AgentSpec:
    name = m.sanitize_name(args.name) if args.name else m.auto_name(prompt or getattr(args, "target", "") or getattr(args, "branch", "") or mode, mode)
    return m.AgentSpec(
        name=name,
        mode=mode,
        repo=args.repo or env("FF_REPO"),
        image=env("FF_IMAGE", "fastfish-agent:latest"),
        base=args.base or "",
        branch=getattr(args, "branch", "") or "",
        prompt=prompt,
        target=getattr(args, "target", "") or "",
        pr=bool(getattr(args, "pr", False)),
        model=args.model or "",
        max_turns=args.max_turns,
        timeout=m.parse_duration(args.timeout),
        ttl=m.parse_duration(args.ttl),
        cpu=args.cpu,
        memory=args.memory,
        cpu_limit=args.cpu_limit,
        memory_limit=args.memory_limit,
        notify=env("FF_NOTIFY"),
        pull_policy=env("FF_PULL_POLICY", "IfNotPresent"),
    )


def launch(args: argparse.Namespace, spec: m.AgentSpec) -> Kube | None:
    job = m.build_job(spec)
    if args.dry_run:
        print(json.dumps(job, indent=2))
        return None
    k = kube()
    k.create(job)
    print(f"started {spec.mode} agent {spec.name}")
    return k


def cmd_run(args: argparse.Namespace) -> int:
    spec = spec_from_args(args, "task", resolve_prompt(args.prompt))
    k = launch(args, spec)
    if k and args.follow:
        return follow_logs(k, spec.name, raw=False, follow=True)
    if k:
        print(f"  follow:  ff logs -f {spec.name}\n  branch:  ff/{spec.name}")
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    if args.repo_pos and not args.repo:
        args.repo = args.repo_pos
    spec = spec_from_args(args, "review", "")
    k = launch(args, spec)
    if k and args.follow:
        return follow_logs(k, spec.name, raw=False, follow=True)
    if k:
        print(f"  follow:  ff logs -f {spec.name}\n  report:  ff out {spec.name}")
    return 0


def cmd_chat(args: argparse.Namespace) -> int:
    spec = spec_from_args(args, "interactive", resolve_prompt(args.prompt))
    k = launch(args, spec)
    if not k or args.no_attach:
        if k:
            print(f"  attach:  ff attach {spec.name}")
        return 0
    return attach(k, spec.name)


def cmd_ls(args: argparse.Namespace) -> int:
    k = kube()
    while True:
        jobs = k.get_json(["jobs", "-l", f"app={m.APP_LABEL}"]).get("items", [])
        pods = pods_by_agent(k)
        rows = []
        for job in sorted(jobs, key=lambda j: j["metadata"]["creationTimestamp"]):
            labels = job["metadata"].get("labels", {})
            name = labels.get("ff/name", job["metadata"]["name"])
            pod = pods.get(name)
            term = termination(pod)
            cost = term.get("cost_usd")
            rows.append([
                name,
                labels.get("ff/mode", "?"),
                agent_status(job, pod),
                age(job["metadata"].get("creationTimestamp")),
                term.get("branch") or "-",
                term.get("pr_url") or "-",
                f"${cost:.2f}" if isinstance(cost, (int, float)) else "-",
            ])
        if args.watch:
            print("\033[2J\033[H", end="")
        print_table(["NAME", "MODE", "STATUS", "AGE", "BRANCH", "PR", "COST"], rows)
        if not rows:
            print("no agents. start one with: ff run \"<prompt>\" --repo <url>")
        if not args.watch:
            return 0
        try:
            time.sleep(3)
        except KeyboardInterrupt:
            return 0


def print_table(header: list[str], rows: list[list[str]]) -> None:
    widths = [max(len(str(r[i])) for r in [header] + rows) for i in range(len(header))]
    for row in [header] + rows:
        print("  ".join(str(c).ljust(w) for c, w in zip(row, widths)).rstrip())


def follow_logs(k: Kube, name: str, raw: bool, follow: bool) -> int:
    pod = wait_for_pod(k, name)
    if pod["metadata"]["labels"].get("ff/mode") == "interactive" and pod["status"].get("phase") == "Running":
        print(f"{name} is interactive; its session lives in tmux. Use: ff attach {name}", file=sys.stderr)
    args = ["logs", pod["metadata"]["name"], "-c", "agent"] + (["-f"] if follow else [])
    proc = k.stream(args)
    try:
        assert proc.stdout is not None
        lines = proc.stdout if raw else render_lines(proc.stdout)
        for line in lines:
            print(line.rstrip("\n") if raw else line, flush=True)
    except KeyboardInterrupt:
        proc.terminate()
        return 130
    return proc.wait()


def cmd_logs(args: argparse.Namespace) -> int:
    return follow_logs(kube(), args.name, raw=args.raw, follow=args.follow)


def running_pod(k: Kube, name: str) -> dict:
    pod = find_pod(k, name)
    if not pod:
        raise KubeError(f"no agent named {name} (see `ff ls`)")
    if pod["status"].get("phase") == "Pending":
        pod = wait_for_pod(k, name)
    if pod["status"].get("phase") != "Running":
        raise KubeError(f"agent {name} is not running ({pod['status'].get('phase')}); see `ff logs {name}`")
    if pod["metadata"]["labels"].get("ff/mode") != "interactive":
        raise KubeError(f"agent {name} is a headless {pod['metadata']['labels'].get('ff/mode')} agent; use `ff logs -f {name}`")
    return pod


def attach(k: Kube, name: str) -> int:
    pod = running_pod(k, name)["metadata"]["name"]
    for _ in range(30):  # tmux starts a moment after the container
        try:
            k.run(["exec", pod, "-c", "agent", "--", "tmux", "has-session", "-t", "agent"])
            break
        except KubeError:
            time.sleep(1)
    print(f"attaching to {name} — detach with Ctrl-b d (the agent keeps running)", file=sys.stderr)
    return k.interactive(["exec", "-it", pod, "-c", "agent", "--", "tmux", "attach", "-t", "agent"])


def cmd_attach(args: argparse.Namespace) -> int:
    return attach(kube(), args.name)


def cmd_send(args: argparse.Namespace) -> int:
    k = kube()
    pod = running_pod(k, args.name)["metadata"]["name"]
    text = resolve_prompt(args.text)
    base = ["exec", pod, "-c", "agent", "--", "tmux", "send-keys", "-t", "agent"]
    k.run(base + ["-l", text])
    k.run(base + ["Enter"])
    print(f"sent to {args.name}")
    return 0


def cmd_out(args: argparse.Namespace) -> int:
    k = kube()
    pod = find_pod(k, args.name)
    if not pod:
        raise KubeError(f"no agent named {args.name} (it may have been cleaned up after its TTL)")
    log = k.run(["logs", pod["metadata"]["name"], "-c", "agent"], timeout=120)
    transcript, report = split_log(log)
    dest = Path(args.dir) / args.name
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "transcript.jsonl").write_text("\n".join(transcript) + ("\n" if transcript else ""))
    (dest / "log.txt").write_text(log)
    written = ["transcript.jsonl", "log.txt"]
    if report:
        (dest / "review.md").write_text(report + "\n")
        written.append("review.md")
    status = termination(pod)
    if status:
        (dest / "status.json").write_text(json.dumps(status, indent=2) + "\n")
        written.append("status.json")
    print(f"{dest}/: {', '.join(written)}")
    return 0


def delete(k: Kube, names: list[str]) -> None:
    for name in names:
        k.run(["delete", "job", m.job_name(name), "--wait=false"])
        print(f"deleted {name}")


def cmd_stop(args: argparse.Namespace) -> int:
    delete(kube(), args.names)
    return 0


def cmd_rm(args: argparse.Namespace) -> int:
    k = kube()
    names = list(args.names)
    if args.all_done:
        pods = pods_by_agent(k)
        for job in k.get_json(["jobs", "-l", f"app={m.APP_LABEL}"]).get("items", []):
            name = job["metadata"]["labels"].get("ff/name", "")
            if agent_status(job, pods.get(name)) in ("done", "failed", "timeout"):
                names.append(name)
    if not names:
        print("nothing to remove")
        return 0
    delete(k, sorted(set(names)))
    return 0


def secret_value(var: str, label: str, interactive: bool) -> str:
    value = env(var)
    if value or not interactive:
        return value
    return getpass.getpass(f"{label} ({var}, Enter to skip): ").strip()


def cmd_setup(args: argparse.Namespace) -> int:
    k = kube()
    k.apply(m.build_namespace(k.namespace), namespaced=False)
    for name in ("serviceaccount.yaml", "policy.yaml"):
        k.apply_file(str(K8S_DIR / name))
    print(f"namespace {k.namespace}: service account, quota and network policy applied")
    if args.skip_secrets:
        return 0
    tty = sys.stdin.isatty()
    oauth = secret_value("CLAUDE_CODE_OAUTH_TOKEN", "Claude subscription token from `claude setup-token`", tty)
    api_key = "" if oauth else secret_value("ANTHROPIC_API_KEY", "Anthropic API key", tty)
    gh = secret_value("GH_TOKEN", "GitHub token for clone/push/PR", tty)
    if oauth or api_key:
        k.apply(m.build_secret(m.SECRET_CLAUDE, {"CLAUDE_CODE_OAUTH_TOKEN": oauth, "ANTHROPIC_API_KEY": api_key}))
        print(f"secret {m.SECRET_CLAUDE}: set ({'subscription token' if oauth else 'API key'})")
    else:
        print(f"secret {m.SECRET_CLAUDE}: unchanged — agents cannot sign in until it exists", file=sys.stderr)
    if gh:
        k.apply(m.build_secret(m.SECRET_GIT, {"GH_TOKEN": gh}))
        print(f"secret {m.SECRET_GIT}: set")
    else:
        print(f"secret {m.SECRET_GIT}: unchanged — only public repos can be cloned, nothing can be pushed")
    return 0


# ---------------------------------------------------------------- parser


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ff", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)

    agent = argparse.ArgumentParser(add_help=False)
    agent.add_argument("--repo", default="", help="git URL to clone (default: $FF_REPO)")
    agent.add_argument("--base", default="", help="branch to start from (default: the repo's default branch)")
    agent.add_argument("--name", default="", help="agent name (default: from the prompt)")
    agent.add_argument("--model", default="", help="Claude model for this agent")
    agent.add_argument("--max-turns", type=int, default=200)
    agent.add_argument("--timeout", default="2h", help="kill the agent after this long (default 2h)")
    agent.add_argument("--ttl", default="3d", help="keep the finished agent and its logs this long (default 3d)")
    agent.add_argument("--cpu", default="500m")
    agent.add_argument("--memory", default="1Gi")
    agent.add_argument("--cpu-limit", default="2")
    agent.add_argument("--memory-limit", default="4Gi")
    agent.add_argument("--dry-run", action="store_true", help="print the Job manifest and exit")

    s = sub.add_parser("setup", help="install namespace, policies and secrets on the cluster")
    s.add_argument("--skip-secrets", action="store_true")
    s.set_defaults(func=cmd_setup)

    s = sub.add_parser("run", parents=[agent], help="start a headless agent on a task")
    s.add_argument("prompt", nargs="+", help="the task, or - to read it from stdin")
    s.add_argument("--pr", action="store_true", help="open a pull request when done")
    s.add_argument("-f", "--follow", action="store_true", help="follow the logs after starting")
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("review", parents=[agent], help="run a fastfish review in the cluster")
    s.add_argument("repo_pos", nargs="?", default="", metavar="REPO")
    s.add_argument("--branch", default="", help="review this branch's changes against --base")
    s.add_argument("--target", default="", help="review these paths instead of a diff")
    s.add_argument("-f", "--follow", action="store_true")
    s.set_defaults(func=cmd_review)

    s = sub.add_parser("chat", parents=[agent], help="start an interactive agent and attach to it")
    s.add_argument("prompt", nargs="*", help="optional first message")
    s.add_argument("--no-attach", action="store_true")
    s.set_defaults(func=cmd_chat)

    s = sub.add_parser("ls", help="list agents")
    s.add_argument("-w", "--watch", action="store_true")
    s.set_defaults(func=cmd_ls)

    s = sub.add_parser("logs", help="show an agent's activity")
    s.add_argument("name")
    s.add_argument("-f", "--follow", action="store_true")
    s.add_argument("--raw", action="store_true", help="raw stream-json")
    s.set_defaults(func=cmd_logs)

    s = sub.add_parser("attach", help="join an interactive agent's terminal")
    s.add_argument("name")
    s.set_defaults(func=cmd_attach)

    s = sub.add_parser("send", help="type a message into an interactive agent")
    s.add_argument("name")
    s.add_argument("text", nargs="+")
    s.set_defaults(func=cmd_send)

    s = sub.add_parser("out", help="download an agent's transcript, review report and status")
    s.add_argument("name")
    s.add_argument("--dir", default="ff-out")
    s.set_defaults(func=cmd_out)

    s = sub.add_parser("stop", help="stop agents (deletes their Jobs)")
    s.add_argument("names", nargs="+")
    s.set_defaults(func=cmd_stop)

    s = sub.add_parser("rm", help="remove agents")
    s.add_argument("names", nargs="*")
    s.add_argument("--all-done", action="store_true", help="remove every finished agent")
    s.set_defaults(func=cmd_rm)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (KubeError, ValueError) as exc:
        print(f"ff: {exc}", file=sys.stderr)
        return 1
