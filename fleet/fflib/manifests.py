"""Pure builders for the Kubernetes objects ff creates. No I/O, so they are easy to test."""
from __future__ import annotations

import re
import secrets
from dataclasses import dataclass

APP_LABEL = "ff-agent"
JOB_PREFIX = "ff-"
MODES = ("task", "review", "interactive")
SECRET_CLAUDE = "claude-auth"
SECRET_GIT = "git-auth"
SERVICE_ACCOUNT = "ff-agent"
AGENT_UID = 1000  # the "node" user in the agent image
MAX_NAME = 40  # job name + pod suffix must stay under the 63-char label limit

_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def sanitize_name(raw: str) -> str:
    """Turn any text into a DNS-1123 label usable as an agent name."""
    name = re.sub(r"[^a-z0-9-]+", "-", raw.lower())
    name = re.sub(r"-{2,}", "-", name).strip("-")[:MAX_NAME].strip("-")
    if not name:
        raise ValueError(f"cannot make an agent name from {raw!r}; pass --name")
    return name


def auto_name(text: str, mode: str) -> str:
    """A short readable name from the first words of the prompt, plus a random suffix."""
    words = re.findall(r"[a-z0-9]+", text.lower())[:4]
    stem = "-".join(words)[:28] or mode
    return sanitize_name(f"{stem}-{secrets.token_hex(2)}")


def parse_duration(value: str | int) -> int:
    """'90s', '30m', '2h', '3d' or plain seconds -> seconds."""
    if isinstance(value, int):
        return value
    m = re.fullmatch(r"\s*(\d+)\s*([smhd]?)\s*", str(value))
    if not m:
        raise ValueError(f"bad duration {value!r}; use e.g. 90s, 30m, 2h, 3d")
    return int(m.group(1)) * _UNITS.get(m.group(2) or "s", 1)


@dataclass
class AgentSpec:
    name: str
    mode: str
    repo: str
    image: str
    base: str = ""
    branch: str = ""
    prompt: str = ""
    target: str = ""
    pr: bool = False
    model: str = ""
    max_turns: int = 200
    timeout: int = 2 * 3600
    ttl: int = 3 * 86400
    cpu: str = "500m"
    memory: str = "1Gi"
    cpu_limit: str = "2"
    memory_limit: str = "4Gi"
    notify: str = ""
    pull_policy: str = "IfNotPresent"

    def validate(self) -> None:
        if self.mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        if sanitize_name(self.name) != self.name:
            raise ValueError(f"invalid agent name {self.name!r}")
        if not self.repo:
            raise ValueError("a repository URL is required (--repo or FF_REPO)")
        if self.mode == "task" and not self.prompt.strip():
            raise ValueError("a task needs a prompt")


def job_name(agent: str) -> str:
    return JOB_PREFIX + agent


def build_job(spec: AgentSpec) -> dict:
    spec.validate()
    labels = {"app": APP_LABEL, "ff/name": spec.name, "ff/mode": spec.mode}
    env = {
        "AGENT_NAME": spec.name,
        "AGENT_MODE": spec.mode,
        "REPO": spec.repo,
        "BASE": spec.base,
        "BRANCH": spec.branch,
        "PROMPT": spec.prompt,
        "TARGET": spec.target,
        "PR": "1" if spec.pr else "0",
        "MODEL": spec.model,
        "MAX_TURNS": str(spec.max_turns),
        "FF_NOTIFY": spec.notify,
    }
    container = {
        "name": "agent",
        "image": spec.image,
        "imagePullPolicy": spec.pull_policy,
        "env": [{"name": k, "value": v} for k, v in env.items()],
        "envFrom": [
            {"secretRef": {"name": SECRET_CLAUDE, "optional": True}},
            {"secretRef": {"name": SECRET_GIT, "optional": True}},
        ],
        "resources": {
            "requests": {"cpu": spec.cpu, "memory": spec.memory},
            "limits": {"cpu": spec.cpu_limit, "memory": spec.memory_limit},
        },
        "securityContext": {
            "runAsNonRoot": True,
            "runAsUser": AGENT_UID,
            "allowPrivilegeEscalation": False,
            "capabilities": {"drop": ["ALL"]},
            "seccompProfile": {"type": "RuntimeDefault"},
        },
        "volumeMounts": [{"name": "work", "mountPath": "/work"}],
        "terminationMessagePolicy": "File",
    }
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": job_name(spec.name),
            "labels": labels,
            "annotations": {
                "ff/repo": spec.repo,
                "ff/base": spec.base,
                "ff/branch": spec.branch,
                "ff/prompt": (spec.prompt or spec.target)[:1000],
            },
        },
        "spec": {
            "backoffLimit": 0,
            "activeDeadlineSeconds": spec.timeout,
            "ttlSecondsAfterFinished": spec.ttl,
            "template": {
                "metadata": {"labels": labels},
                "spec": {
                    "restartPolicy": "Never",
                    "serviceAccountName": SERVICE_ACCOUNT,
                    "automountServiceAccountToken": False,
                    "securityContext": {"fsGroup": AGENT_UID},
                    "containers": [container],
                    "volumes": [{"name": "work", "emptyDir": {}}],
                },
            },
        },
    }


def build_namespace(namespace: str) -> dict:
    return {"apiVersion": "v1", "kind": "Namespace", "metadata": {"name": namespace}}


def build_secret(name: str, data: dict[str, str]) -> dict:
    return {
        "apiVersion": "v1",
        "kind": "Secret",
        "type": "Opaque",
        "metadata": {"name": name, "labels": {"app": APP_LABEL}},
        "stringData": {k: v for k, v in data.items() if v},
    }
