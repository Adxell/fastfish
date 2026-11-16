"""Unit tests for ff. No cluster or kubectl needed: python3 -m unittest discover fleet/tests"""
import contextlib
import io
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fflib import cli, manifests as m  # noqa: E402
from fflib.render import REPORT_END, REPORT_START, render_lines, split_log  # noqa: E402


def spec(**kw):
    base = dict(name="fix-login", mode="task", repo="https://github.com/o/r.git", image="img:1", prompt="fix login")
    base.update(kw)
    return m.AgentSpec(**base)


class Names(unittest.TestCase):
    def test_sanitize(self):
        self.assertEqual(m.sanitize_name("Fix  the LOGIN_bug!"), "fix-the-login-bug")
        self.assertLessEqual(len(m.sanitize_name("x" * 100)), m.MAX_NAME)
        with self.assertRaises(ValueError):
            m.sanitize_name("!!!")

    def test_auto_name_is_valid_and_unique(self):
        a, b = m.auto_name("Add dark mode to settings page please", "task"), m.auto_name("Add dark mode", "task")
        self.assertEqual(a, m.sanitize_name(a))
        self.assertTrue(a.startswith("add-dark-mode-to"))
        self.assertNotEqual(a, b)
        self.assertTrue(m.auto_name("¿¿", "review").startswith("review-"))

    def test_duration(self):
        self.assertEqual(m.parse_duration("90s"), 90)
        self.assertEqual(m.parse_duration("30m"), 1800)
        self.assertEqual(m.parse_duration("2h"), 7200)
        self.assertEqual(m.parse_duration("3d"), 259200)
        self.assertEqual(m.parse_duration("45"), 45)
        with self.assertRaises(ValueError):
            m.parse_duration("2 hours")


class Job(unittest.TestCase):
    def test_shape(self):
        job = m.build_job(spec(pr=True, timeout=600))
        self.assertEqual(job["metadata"]["name"], "ff-fix-login")
        self.assertEqual(job["metadata"]["labels"], {"app": "ff-agent", "ff/name": "fix-login", "ff/mode": "task"})
        js = job["spec"]
        self.assertEqual(js["backoffLimit"], 0)
        self.assertEqual(js["activeDeadlineSeconds"], 600)
        pod = js["template"]["spec"]
        self.assertEqual(pod["restartPolicy"], "Never")
        self.assertFalse(pod["automountServiceAccountToken"])
        self.assertEqual(js["template"]["metadata"]["labels"]["ff/name"], "fix-login")
        c = pod["containers"][0]
        env = {e["name"]: e["value"] for e in c["env"]}
        self.assertEqual(env["PR"], "1")
        self.assertEqual(env["PROMPT"], "fix login")
        self.assertEqual(env["AGENT_MODE"], "task")
        refs = [(r["secretRef"]["name"], r["secretRef"]["optional"]) for r in c["envFrom"]]
        self.assertEqual(refs, [("claude-auth", True), ("git-auth", True)])
        self.assertTrue(c["securityContext"]["runAsNonRoot"])
        self.assertFalse(c["securityContext"]["allowPrivilegeEscalation"])
        self.assertEqual(c["securityContext"]["runAsUser"], m.AGENT_UID)

    def test_no_secret_values_in_job(self):
        self.assertNotIn("TOKEN", json.dumps(m.build_job(spec())).replace("secretRef", ""))

    def test_validation(self):
        with self.assertRaises(ValueError):
            m.build_job(spec(mode="nope"))
        with self.assertRaises(ValueError):
            m.build_job(spec(repo=""))
        with self.assertRaises(ValueError):
            m.build_job(spec(prompt="  "))
        with self.assertRaises(ValueError):
            m.build_job(spec(name="Bad Name"))
        m.build_job(spec(mode="review", prompt="", target="src"))  # review needs no prompt

    def test_secret_drops_empty(self):
        s = m.build_secret("claude-auth", {"CLAUDE_CODE_OAUTH_TOKEN": "t", "ANTHROPIC_API_KEY": ""})
        self.assertEqual(s["stringData"], {"CLAUDE_CODE_OAUTH_TOKEN": "t"})


class Cli(unittest.TestCase):
    def run_cli(self, argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cli.main(argv)
        return code, out.getvalue()

    def test_run_dry_run_needs_no_cluster(self):
        code, out = self.run_cli(["run", "add", "a", "README", "--repo", "https://x/y.git", "--name", "readme", "--dry-run", "--timeout", "30m"])
        self.assertEqual(code, 0)
        job = json.loads(out)
        self.assertEqual(job["metadata"]["name"], "ff-readme")
        self.assertEqual(job["spec"]["activeDeadlineSeconds"], 1800)
        env = {e["name"]: e["value"] for e in job["spec"]["template"]["spec"]["containers"][0]["env"]}
        self.assertEqual(env["PROMPT"], "add a README")

    def test_review_positional_repo(self):
        code, out = self.run_cli(["review", "https://x/y.git", "--branch", "feat", "--dry-run"])
        self.assertEqual(code, 0)
        job = json.loads(out)
        env = {e["name"]: e["value"] for e in job["spec"]["template"]["spec"]["containers"][0]["env"]}
        self.assertEqual((env["AGENT_MODE"], env["REPO"], env["BRANCH"]), ("review", "https://x/y.git", "feat"))

    def test_missing_repo_is_an_error(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code, _ = self.run_cli(["run", "x", "--dry-run"])
        self.assertEqual(code, 1)
        self.assertIn("repository", err.getvalue())

    def test_status(self):
        done = {"status": {"conditions": [{"type": "Complete", "status": "True"}]}}
        late = {"status": {"conditions": [{"type": "Failed", "status": "True", "reason": "DeadlineExceeded"}]}}
        self.assertEqual(cli.agent_status(done, None), "done")
        self.assertEqual(cli.agent_status(late, None), "timeout")
        pulling = {"status": {"phase": "Pending", "containerStatuses": [{"state": {"waiting": {"reason": "ImagePullBackOff"}}}]}}
        self.assertEqual(cli.agent_status({"status": {"active": 1}}, pulling), "ImagePullBackOff")
        self.assertEqual(cli.agent_status({"status": {"active": 1}}, {"status": {"phase": "Running"}}), "running")

    def test_termination_message(self):
        pod = {"status": {"containerStatuses": [{"state": {"terminated": {"message": '{"branch": "ff/x", "cost_usd": 0.4}'}}}]}}
        self.assertEqual(cli.termination(pod)["branch"], "ff/x")
        self.assertEqual(cli.termination(None), {})


class Render(unittest.TestCase):
    def test_render(self):
        events = [
            '[ff] agent x (task) cloning repo',
            json.dumps({"type": "system", "subtype": "init", "model": "claude-opus-5-5"}),
            json.dumps({"type": "assistant", "message": {"content": [
                {"type": "text", "text": "Looking at the code."},
                {"type": "tool_use", "name": "Bash", "input": {"command": "npm test"}}]}}),
            json.dumps({"type": "user", "message": {"content": [{"type": "tool_result", "is_error": True, "content": "boom"}]}}),
            json.dumps({"type": "result", "num_turns": 3, "duration_ms": 12000, "total_cost_usd": 0.1234}),
            "{not json",
        ]
        out = list(render_lines(events))
        self.assertEqual(out[0], "[ff] agent x (task) cloning repo")
        self.assertIn("claude-opus-5-5", out[1])
        self.assertIn("Looking at the code.", out)
        self.assertIn("  → Bash: npm test", out)
        self.assertIn("  ✗ boom", out)
        self.assertEqual(out[-2], "■ done · 3 turns · 12s · $0.12")
        self.assertEqual(out[-1], "{not json")

    def test_split_log(self):
        log = "\n".join(["[ff] hi", '{"type":"result"}', REPORT_START, "# fastfish review", "## Major", REPORT_END, "[ff] finished"])
        transcript, report = split_log(log)
        self.assertEqual(transcript, ['{"type":"result"}'])
        self.assertEqual(report, "# fastfish review\n## Major")


if __name__ == "__main__":
    unittest.main()
