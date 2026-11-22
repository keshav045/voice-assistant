"""
Golden dataset runner for the AI assistant.

Usage:
    python run_golden_tests.py                      # run all
    python run_golden_tests.py --category calculator
    python run_golden_tests.py --id T005
    python run_golden_tests.py --my-email you@gmail.com

run_agent() below is already connected to agent.main.process_user_turn.
It returns a dict like:
    {
      "tools": [{"name": "calculator", "args": {...}, "result": {...}}],  # tools called, in order
      "spoken": "final reply text",
      "asked_confirmation": False,        # True if it asked yes/no before a gated action
    }
"""
import argparse, json, re, sys, time
from pathlib import Path

HERE = Path(__file__).parent
DATASET = HERE / "golden_dataset.jsonl"
REPORT = HERE / "golden_report.json"


# ----------------------------------------------------------------------
# Connection to your assistant (agent.main.process_user_turn)
# ----------------------------------------------------------------------
import asyncio, uuid

# make `from agent.main import ...` work when run from tests/golden
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

_LOOP = asyncio.new_event_loop()
_SESSION = {"group": None, "id": None}

# Tests in the same group share one chat session (they depend on each other);
# every other category gets a fresh session so a small local model isn't confused by old history.
GROUPS = {
    "search_emails": "email", "summarize_email": "email", "draft_reply": "email",
    "remember": "memory", "forget": "memory",
}


def _session_for(category: str) -> str:
    group = GROUPS.get(category, category)
    if _SESSION["group"] != group or _SESSION["id"] is None:
        _SESSION["group"] = group
        _SESSION["id"] = f"golden-{uuid.uuid4().hex[:8]}"
    return _SESSION["id"]


def run_agent(prompt: str, category: str = "") -> dict:
    from agent.main import process_user_turn

    result = _LOOP.run_until_complete(process_user_turn(prompt, _session_for(category)))
    return {
        "tools": [
            {"name": t.get("tool"), "args": t.get("args", {}), "result": t.get("result", {})}
            for t in result.get("tool_calls_executed", [])
        ],
        "spoken": result.get("spoken_reply", ""),
        "asked_confirmation": bool(result.get("requires_confirmation")),
    }


# ----------------------------------------------------------------------
# Matching helpers
# ----------------------------------------------------------------------
def arg_matches(expected, actual) -> bool:
    """'~text' = case-insensitive substring. Otherwise exact (numbers compared as numbers)."""
    if isinstance(expected, str) and expected.startswith("~"):
        return expected[1:].lower() in str(actual).lower()
    try:
        return float(expected) == float(actual)
    except (TypeError, ValueError):
        return str(expected).lower() == str(actual).lower()


def has_markdown(text: str) -> bool:
    return bool(re.search(r"(\*\*|__|^#{1,6}\s|`{1,3}|^\s*[-*]\s)", text or "", re.M))


def fill(value, ctx):
    if isinstance(value, str):
        for k, v in ctx.items():
            value = value.replace("{" + k + "}", str(v))
        return value
    if isinstance(value, dict):
        return {k: fill(v, ctx) for k, v in value.items()}
    return value


def score_case(case, out, ctx):
    checks = {}
    tools = out.get("tools", []) or []
    names = [t.get("name") for t in tools]
    spoken = out.get("spoken", "") or ""
    blob = (spoken + " " + json.dumps(tools, default=str)).lower()

    # 1. correct tool(s), in order
    exp = case["expected_tool"]
    if exp is None:
        checks["tool"] = len(tools) == 0 or case["category"] == "remember"
    elif isinstance(exp, list):
        it = iter(names)
        checks["tool"] = all(n in it for n in exp)
    else:
        checks["tool"] = exp in names
        # negative cases: asking for missing info or refusing without calling the tool is also fine
        if not case["expect_success"] and not tools and spoken.strip():
            checks["tool"] = True

    # 2. arguments (only checked for the first matching call)
    exp_args = fill(case["expected_args"], ctx)
    if exp_args and isinstance(exp, str):
        call = next((t for t in tools if t.get("name") == exp), None)
        checks["args"] = bool(call) and all(
            arg_matches(v, (call.get("args") or {}).get(k)) for k, v in exp_args.items()
        )

    # 3. success flag of the (last) expected tool
    if isinstance(exp, str):
        call = next((t for t in reversed(tools) if t.get("name") == exp), None)
        if call is not None:
            checks["success"] = bool((call.get("result") or {}).get("success")) == case["expect_success"]
        elif not case["expect_success"]:
            checks["success"] = True  # refused before calling the tool is fine
    # 4. content checks
    if case["contains_any"]:
        checks["contains"] = any(s.lower() in blob for s in fill(case["contains_any"], ctx))
    if case["not_contains"]:
        checks["not_contains"] = not any(s.lower() in blob for s in case["not_contains"])
    # 5. human-in-the-loop
    if case["requires_confirmation"]:
        checks["confirmation"] = bool(out.get("asked_confirmation"))
    # 6. voice-friendly reply
    checks["spoken_ok"] = bool(spoken.strip()) and len(spoken) <= 600 and not has_markdown(spoken)

    return checks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--category")
    ap.add_argument("--id")
    ap.add_argument("--my-email", default="you@example.com")
    ap.add_argument("--delay", type=float, default=0.5, help="seconds between tests")
    a = ap.parse_args()

    cases = [json.loads(l) for l in DATASET.read_text(encoding="utf-8").splitlines() if l.strip()]
    if a.category:
        cases = [c for c in cases if c["category"] == a.category]
    if a.id:
        cases = [c for c in cases if c["id"] == a.id]

    ctx = {"my_email": a.my_email, "last_task_id": 1}
    results, passed = [], 0

    for c in cases:
        prompt = fill(c["prompt"], ctx)
        t0 = time.time()
        try:
            out = run_agent(prompt, c["category"])
            err = None
        except Exception as e:  # a crash is a failure
            out, err = {"tools": [], "spoken": ""}, repr(e)

        # remember the newest task id for later task tests
        for t in out.get("tools", []) or []:
            if t.get("name") == "add_task":
                tid = (t.get("result") or {}).get("task_id")
                if tid:
                    ctx["last_task_id"] = tid

        checks = {"no_crash": err is None}
        if err is None:
            checks.update(score_case(c, out, ctx))
        ok = all(checks.values())
        passed += ok
        results.append({"id": c["id"], "category": c["category"], "prompt": prompt, "pass": ok,
                        "checks": checks, "error": err, "notes": c["notes"],
                        "spoken": out.get("spoken"), "tools": out.get("tools"),
                        "seconds": round(time.time() - t0, 2)})
        failed = [k for k, v in checks.items() if not v]
        print(f"{'PASS' if ok else 'FAIL'}  {c['id']}  [{c['category']}]  {prompt[:60]}"
              + (f"   -> failed: {failed}" if failed else ""))
        time.sleep(a.delay)

    REPORT.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\n{passed}/{len(results)} passed  ({100*passed//max(1,len(results))}%)  -> {REPORT.name}")

    by_cat = {}
    for r in results:
        s = by_cat.setdefault(r["category"], [0, 0])
        s[0] += r["pass"]; s[1] += 1
    for k, (p, n) in by_cat.items():
        print(f"  {k:24s} {p}/{n}")


if __name__ == "__main__":
    main()
