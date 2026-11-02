"""Long-term memory tools for facts and user preferences."""

from typing import Any, Dict
from db.models import db_add_fact, db_forget_fact, db_list_facts


def remember(fact: str, category: str = "general") -> Dict[str, Any]:
    """Store a personal fact or preference in long-term memory."""
    res = db_add_fact(fact=fact, category=category)
    return {
        "success": True,
        "fact": res,
        "spoken": f"I will remember that: {fact}.",
    }


def forget(fact: str) -> Dict[str, Any]:
    """Remove a fact or preference from memory."""
    ok = db_forget_fact(fact_query=fact)
    if ok:
        return {"success": True, "spoken": f"I have forgotten: {fact}."}
    return {"success": False, "spoken": f"I could not find memory matching '{fact}' to remove."}

