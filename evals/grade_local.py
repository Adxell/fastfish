"""Keyword grading for run_local.sh results.

A case passes if the answer names the planted problem (patterns in the case's
checks.json, or CHECKS below). "Clean" cases pass if the answer discusses the
change and rates nothing as serious. In the fastfish arm a review case also
needs a fastfish report on disk, so a hand-made fallback review does not count.
Usage: grade_local.py <arm_results_dir> [fastfish|plain|egm]
"""
import json, pathlib, re, sys

out = pathlib.Path(sys.argv[1])
arm = sys.argv[2] if len(sys.argv) > 2 else "fastfish"
evals = pathlib.Path(__file__).parent
CHECKS = {
    "rule-route-uses-repo": [r"routes/orders", r"repo|db\.ts|findOrder", r"layer|architecture|service"],
    "rule-float-money": [r"shippingFee|shipping", r"cents", r"4\.99|float|dollar"],
    "rule-nested-admin": [r"/admin/orders/count|count route|count endpoint", r"requireAdmin"],
    "bug-idor": [r"getOrder", r"userId|owner|belongs|another user|any user|IDOR|authori"],
    "bug-stock-race": [r"reserveStock", r"race|oversell|atomic|concurr|two steps|read.{0,20}write"],
    "clean-change": "CLEAN:cartItemCount|/cart/count",
}
SERIOUS = re.compile(r"\b[1-9]\d*\s*\**\s*(blockers?|majors?|high|critical)\b|\b(blockers?|majors?)\**\s*[:(]\s*\**[1-9]|^#+\s*(blocker|major|high|critical)\b(?!s?\s*[:(]?\s*(0|none))", re.I | re.M)

def checks_for(case):
    f = evals / case / "checks.json"
    if f.exists():
        c = json.loads(f.read_text())
        return "CLEAN:reserveLines|totalOf|helper|refactor" if c == "CLEAN" else c
    return CHECKS.get(case)

rows, passed = [], 0
for d in sorted(p for p in out.iterdir() if p.is_dir()):
    c = d.name
    try:
        r = json.loads((d / "result.json").read_text())
        text, cost = r.get("result", ""), r.get("total_cost_usd", 0)
    except Exception as e:
        text, cost = f"(no result: {e})", 0
    (d / "answer.md").write_text(text)
    secs = (d / "seconds").read_text().strip() if (d / "seconds").exists() else "?"
    reviews = d / "workspace" / ".fastfish" / "reviews"
    fired = reviews.exists() and any(reviews.iterdir())
    need_fired = arm == "fastfish"
    chk = checks_for(c)
    if c == "no-fire-explain":
        ok = not fired and bool(re.search(r"reserveStock|stock", text, re.I))
    elif isinstance(chk, str) and chk.startswith("CLEAN:"):
        ok = bool(re.search(chk[6:], text)) and not SERIOUS.search(text) and (fired or not need_fired)
    else:
        ok = all(re.search(p, text, re.I) for p in chk) and (fired or not need_fired)
    passed += ok
    rows.append(f"{'PASS' if ok else 'FAIL'}  {c:22} {secs:>5}s  ${cost:.2f}  fastfish report: {'yes' if fired else 'no'}")
print(f"[{arm}]")
print("\n".join(rows))
print(f"{passed}/{len(rows)} passed · results in {out}")
