"""Thin kubectl wrapper. Every cluster call in ff goes through here."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys


class KubeError(RuntimeError):
    pass


class Kube:
    def __init__(self, namespace: str, context: str = "") -> None:
        if not shutil.which("kubectl"):
            raise KubeError("kubectl not found on PATH. Install it and point your kubeconfig at the server.")
        self.namespace = namespace
        self.base = ["kubectl"] + (["--context", context] if context else [])

    def _cmd(self, args: list[str], namespaced: bool = True) -> list[str]:
        return self.base + (["-n", self.namespace] if namespaced else []) + args

    def run(self, args: list[str], stdin: str | None = None, namespaced: bool = True, timeout: int = 60) -> str:
        try:
            res = subprocess.run(
                self._cmd(args, namespaced), input=stdin, capture_output=True, text=True, timeout=timeout
            )
        except subprocess.TimeoutExpired as exc:
            raise KubeError(f"kubectl {' '.join(args[:2])} timed out after {timeout}s") from exc
        if res.returncode != 0:
            raise KubeError(res.stderr.strip() or f"kubectl {' '.join(args[:2])} failed")
        return res.stdout

    def get_json(self, args: list[str]) -> dict:
        return json.loads(self.run(["get"] + args + ["-o", "json"]))

    def apply(self, obj: dict, namespaced: bool = True) -> str:
        """Apply an object through stdin, so secret values never appear in the process list."""
        return self.run(["apply", "-f", "-"], stdin=json.dumps(obj), namespaced=namespaced)

    def create(self, obj: dict) -> str:
        """Create (not apply), so reusing a running agent's name fails loudly instead of patching it."""
        return self.run(["create", "-f", "-"], stdin=json.dumps(obj))

    def apply_file(self, path: str) -> str:
        return self.run(["apply", "-f", path])

    def stream(self, args: list[str]) -> subprocess.Popen:
        return subprocess.Popen(self._cmd(args), stdout=subprocess.PIPE, text=True, bufsize=1)

    def interactive(self, args: list[str]) -> int:
        """Run with the user's terminal attached (exec -it, attach)."""
        try:
            return subprocess.call(self._cmd(args))
        except KeyboardInterrupt:
            print(file=sys.stderr)
            return 130
