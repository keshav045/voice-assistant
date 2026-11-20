"""Quality gate checker for continuous integration and model promotion."""

import json
import os
import sys
from typing import Any, Dict


def check_promotion_readiness(report: Dict[str, Any]) -> bool:
    """Validate that evaluation results meet production criteria before promotion."""
    summary = report.get("summary", {})
    pass_rate = summary.get("pass_rate_pct", 0.0)
    failed = summary.get("failed_tests", 999)

    min_pass_rate = 90.0
    max_allowed_failures = 0

    is_promotable = (pass_rate >= min_pass_rate) and (failed <= max_allowed_failures)

    print("=" * 64)
    print("  PRODUCTION PROMOTION GATE CHECK")
    print("=" * 64)
    print(f"  Current Pass Rate: {pass_rate}% (Minimum Required: {min_pass_rate}%)")
    print(f"  Failed Tests:      {failed} (Maximum Allowed: {max_allowed_failures})")
    print(f"  PROMOTION STATUS:  {'[PASS] APPROVED FOR PRODUCTION' if is_promotable else '[FAIL] BLOCKED (Quality Gate Failed)'}")
    print("=" * 64)

    return is_promotable


if __name__ == "__main__":
    report_file = os.path.join(os.path.dirname(__file__), "suite_report.json")
    if os.path.exists(report_file):
        with open(report_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        ok = check_promotion_readiness(data)
        sys.exit(0 if ok else 1)
    else:
        print(f"No suite_report.json found at {report_file}. Run run_suite.py first.")
        sys.exit(1)
