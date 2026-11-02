"""Memory loader and manager for long-term facts."""

from typing import List
from db.models import db_list_facts, db_add_fact, db_forget_fact


def get_memory_context() -> str:
    """Format active user facts into a concise system prompt context block."""
    facts = db_list_facts()
    if not facts:
        return ""

    lines = ["Known user preferences and facts:"]
    for f in facts[:15]:
        lines.append(f"- {f['fact']}")
    return "\n".join(lines)


def store_fact(fact: str, category: str = "general") -> None:
    """Save a new fact into memory."""
    db_add_fact(fact=fact, category=category)


def delete_fact(fact_keyword: str) -> bool:
    """Forget a fact from memory."""
    return db_forget_fact(fact_query=fact_keyword)

