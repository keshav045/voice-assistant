"""Evaluates system reliability, error recovery, and graceful failure handling."""

import os
import sys
from typing import Any, Dict

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from agent.tools import TOOLS_REGISTRY
from evals.harness import EvalHarness


def run_reliability_eval(harness: EvalHarness) -> Dict[str, Any]:
    tests = []

    # 1. Division by Zero
    c_res = TOOLS_REGISTRY["calculator"](expression="1000 / 0")
    div_zero_handled = c_res.get("success") is False and "division by zero" in c_res.get("error", "").lower()
    tests.append(("Division by Zero", div_zero_handled, "Caught and reported without crash"))

    # 2. Syntax Error
    s_res = TOOLS_REGISTRY["calculator"](expression="((45 + 12")
    syntax_handled = s_res.get("success") is False and bool(s_res.get("error"))
    tests.append(("Math Syntax Error", syntax_handled, "Handled unclosed parentheses gracefully"))

    # 3. Code Injection / Malicious Sandbox Execution
    py_res = TOOLS_REGISTRY["run_python_code"](code="import os\nos.system('echo hacked')")
    py_blocked = py_res.get("success") is False and "security restriction" in py_res.get("error", "").lower()
    tests.append(("Malicious Code Injection Blocking", py_blocked, "Blocked os.system in Python sandbox"))

    # 4. Unknown App Launcher fallback
    app_res = TOOLS_REGISTRY["open_app"](name="nonexistent_xyz_app_999")
    app_handled = (app_res.get("success") is False and "could not find" in app_res.get("spoken", "").lower()) or ("google.com" in app_res.get("url", ""))
    tests.append(("Unknown App Launcher Fallback", app_handled, "Handled unrecognized app safely without crash"))

    # 5. Invalid Timezone fallback
    tz_res = TOOLS_REGISTRY["get_current_time"](timezone_str="Invalid/Nonexistent")
    tz_handled = tz_res.get("success") is True
    tests.append(("Invalid Timezone Fallback", tz_handled, "Fell back safely to UTC"))

    all_passed = all(t[1] for t in tests)
    for name, passed, detail in tests:
        harness.record_test("eval_reliability", name, passed, passed, detail)

    return {
        "tests_run": len(tests),
        "passed": sum(1 for t in tests if t[1]),
        "reliability_pct": round((sum(1 for t in tests if t[1]) / len(tests)) * 100, 1),
    }


if __name__ == "__main__":
    h = EvalHarness()
    run_reliability_eval(h)
