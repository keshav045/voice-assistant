"""Long-term memory tools for facts and user preferences."""

from typing import Any, Dict, Optional, Union
from db.models import db_add_fact, db_forget_fact, db_list_facts


def remember(
    fact: Union[str, Dict[str, Any]],
    category: str = "general",
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Store a personal fact or preference in long-term memory."""
    if isinstance(fact, dict):
        category = fact.get("category", category)
        fact = fact.get("fact") or str(fact)
    fact_str = str(fact).strip()
    res = db_add_fact(fact=fact_str, category=category, user_id=user_id)
    return {
        "success": True,
        "fact": res,
        "spoken": f"I will remember that: {fact_str}.",
    }


def forget(
    fact: Union[str, Dict[str, Any]],
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Remove a fact or preference from memory."""
    if isinstance(fact, dict):
        fact = fact.get("fact") or str(fact)
    fact_str = str(fact).strip()
    db_forget_fact(fact_query=fact_str, user_id=user_id)
    return {"success": True, "spoken": f"I have forgotten: {fact_str}."}
