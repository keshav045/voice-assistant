"""Safe Python code runner tool for coding assistance, mathematical calculations, and algorithmic reasoning."""

import contextlib
import io
import math
import traceback
from typing import Any, Dict


def run_python_code(code: str) -> Dict[str, Any]:
    """Execute a Python code snippet safely, capturing stdout output.
    
    Args:
        code: Python source code string to execute.
        
    Returns:
        Dict with success status, stdout output, and spoken summary.
    """
    clean_code = code.strip()
    if not clean_code:
        return {"success": False, "output": "No code provided.", "spoken": "No code was provided to run."}

    # Safety checks: block destructive OS / filesystem / network operations
    blocked_keywords = [
        "os.system", "shutil", "subprocess", "rmdir", "unlink", "socket",
        "open(", "__import__", "importlib", "sys.exit", "os.remove"
    ]
    for b in blocked_keywords:
        if b in clean_code:
            return {
                "success": False,
                "error": f"Security restriction: '{b}' is blocked.",
                "spoken": "I cannot execute code containing system file or network operations.",
            }

    stdout_capture = io.StringIO()
    safe_globals = {
        "__builtins__": {
            "print": print,
            "range": range,
            "len": len,
            "int": int,
            "float": float,
            "str": str,
            "bool": bool,
            "list": list,
            "dict": dict,
            "set": set,
            "tuple": tuple,
            "sum": sum,
            "min": min,
            "max": max,
            "abs": abs,
            "round": round,
            "enumerate": enumerate,
            "zip": zip,
            "map": map,
            "filter": filter,
            "sorted": sorted,
            "reversed": reversed,
            "isinstance": isinstance,
            "any": any,
            "all": all,
        },
        "math": math,
    }

    try:
        with contextlib.redirect_stdout(stdout_capture):
            exec(clean_code, safe_globals)
        output = stdout_capture.getvalue().strip()
        if not output:
            output = "Code executed successfully (no stdout produced)."
        # Limit output length for spoken readability
        spoken_out = output[:200] + ("..." if len(output) > 200 else "")
        return {
            "success": True,
            "code": clean_code,
            "output": output,
            "spoken": f"The code executed successfully. Output: {spoken_out}",
        }
    except Exception as e:
        err_msg = traceback.format_exc().splitlines()[-1]
        return {
            "success": False,
            "code": clean_code,
            "error": err_msg,
            "spoken": f"Code execution returned an error: {err_msg}",
        }

