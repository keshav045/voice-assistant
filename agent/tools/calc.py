"""Safe calculator tool using Python's ast module (no eval)."""

import ast
import math
import operator
from typing import Any, Dict

# Allowed operators
_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
}

# Allowed math functions (safe subset)
_FUNCS = {
    "sqrt": math.sqrt,
    "abs": abs,
    "round": round,
    "floor": math.floor,
    "ceil": math.ceil,
    "log": math.log,
    "log10": math.log10,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "pi": math.pi,
    "e": math.e,
}


def _safe_eval(node: ast.AST) -> float:
    """Recursively evaluate an AST node safely."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return float(node.value)
        raise ValueError(f"Unsupported constant: {node.value}")

    if isinstance(node, ast.Name):
        if node.id in _FUNCS:
            val = _FUNCS[node.id]
            if callable(val):
                raise ValueError(f"Call {node.id}() with arguments")
            return float(val)
        raise ValueError(f"Unknown name: {node.id}")

    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _OPS:
            raise ValueError(f"Unsupported operator: {op_type.__name__}")
        left = _safe_eval(node.left)
        right = _safe_eval(node.right)
        if op_type == ast.Div and right == 0:
            raise ZeroDivisionError("Division by zero")
        return _OPS[op_type](left, right)

    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _OPS:
            raise ValueError(f"Unsupported unary operator: {op_type.__name__}")
        return _OPS[op_type](_safe_eval(node.operand))

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("Only simple function calls are allowed")
        func_name = node.func.id
        if func_name not in _FUNCS or not callable(_FUNCS[func_name]):
            raise ValueError(f"Unknown or non-callable function: {func_name}")
        args = [_safe_eval(a) for a in node.args]
        return _FUNCS[func_name](*args)

    raise ValueError(f"Unsupported expression type: {type(node).__name__}")


def calculator(expression: str) -> Dict[str, Any]:
    """Evaluate a mathematical expression safely.

    Supports: +, -, *, /, **, %, //, sqrt(), abs(), round(), floor(),
    ceil(), log(), log10(), sin(), cos(), tan(), pi, e.

    Args:
        expression: A math expression string, e.g. "15% of 2340" or "sqrt(144) + 2**8"

    Returns:
        Dict with result, spoken answer, and formatted expression.
    """
    raw = expression.strip()

    # Normalize inline or full "X% of Y" -> "((X/100) * Y)"
    import re
    raw = re.sub(
        r"(\d+(?:\.\d+)?)\s*%\s*of\s*(\(?\d+(?:\.\d+)?\)?)",
        r"((\1/100) * \2)",
        raw,
        flags=re.IGNORECASE,
    )

    try:
        tree = ast.parse(raw, mode="eval")
        result = _safe_eval(tree.body)

        # Format result nicely
        if result == int(result) and abs(result) < 1e15:
            result_fmt = str(int(result))
        else:
            result_fmt = f"{result:,.6g}"

        return {
            "success": True,
            "expression": expression,
            "result": result,
            "spoken": f"The answer is {result_fmt}.",
            "formatted": result_fmt,
        }
    except ZeroDivisionError:
        return {
            "success": False,
            "expression": expression,
            "error": "Division by zero",
            "spoken": "That expression involves division by zero, which is undefined.",
        }
    except Exception as exc:
        return {
            "success": False,
            "expression": expression,
            "error": str(exc),
            "spoken": f"I could not calculate that expression. {exc}",
        }

