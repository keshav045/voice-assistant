"""Safe Python code runner tool for coding assistance, mathematical calculations, and algorithmic reasoning."""

import ast
import subprocess
import sys
from typing import Any, Dict


def run_python_code(code: str) -> Dict[str, Any]:
    """Execute a Python code snippet safely with AST inspection and timeout protection.
    
    Args:
        code: Python source code string to execute.
        
    Returns:
        Dict with success status, stdout output, and spoken summary.
    """
    clean_code = code.strip()
    if not clean_code:
        return {"success": False, "output": "No code provided.", "spoken": "No code was provided to run."}

    # AST validation: inspect imported modules and dangerous builtins
    try:
        tree = ast.parse(clean_code)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [alias.name for alias in getattr(node, "names", [])]
                module_name = getattr(node, "module", "") or ""
                all_mods = names + ([module_name] if module_name else [])
                for m in all_mods:
                    if any(blocked in m for blocked in ["os", "subprocess", "sys", "shutil", "socket", "importlib", "urllib", "requests"]):
                        return {
                            "success": False,
                            "error": f"Security restriction: module '{m}' is blocked by AST check.",
                            "spoken": f"Security restriction: module '{m}' is blocked.",
                        }
            if isinstance(node, ast.Call):
                # Check for open(), exec(), eval(), __import__()
                if isinstance(node.func, ast.Name) and node.func.id in ["open", "__import__", "exec", "eval"]:
                    return {
                        "success": False,
                        "error": f"Security restriction: '{node.func.id}' is blocked.",
                        "spoken": f"Security restriction: function '{node.func.id}' is blocked.",
                    }
                elif isinstance(node.func, ast.Attribute) and node.func.attr in ["system", "popen", "remove", "unlink", "rmdir"]:
                    return {
                        "success": False,
                        "error": f"Security restriction: '{node.func.attr}' is blocked.",
                        "spoken": f"Security restriction: '{node.func.attr}' is blocked.",
                    }
    except SyntaxError as syn_err:
        return {
            "success": False,
            "error": f"SyntaxError: {syn_err}",
            "spoken": f"Syntax error in code: {syn_err}",
        }

    # Execute in an isolated subprocess with hard 2.5 second timeout
    try:
        proc = subprocess.run(
            [sys.executable, "-c", clean_code],
            capture_output=True,
            text=True,
            timeout=2.5,
        )
        if proc.returncode != 0:
            err_line = (proc.stderr or "").strip().splitlines()[-1] if (proc.stderr or "").strip() else "Non-zero exit code"
            return {
                "success": False,
                "code": clean_code,
                "error": err_line,
                "spoken": f"Code execution returned an error: {err_line}",
            }
        
        output = (proc.stdout or "").strip()
        if not output:
            output = "Code executed successfully with no stdout output."
        spoken_out = output[:200] + ("..." if len(output) > 200 else "")
        return {
            "success": True,
            "code": clean_code,
            "output": output,
            "spoken": f"The code executed successfully. Output: {spoken_out}",
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "code": clean_code,
            "error": "Execution timed out after 2.5 seconds.",
            "spoken": "Code execution timed out.",
        }
    except Exception as e:
        return {
            "success": False,
            "code": clean_code,
            "error": str(e),
            "spoken": f"Execution failed: {e}",
        }
