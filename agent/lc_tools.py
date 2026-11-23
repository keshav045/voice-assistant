"""LangChain tool wrappers for Nexus AI Assistant.

Wraps existing tool implementations with @tool and integrates LangGraph interrupt()
for human-in-the-loop approval before executing irreversible actions.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from langchain_core.tools import tool
from langgraph.types import interrupt

from agent.tools import (
    calc as calc_impl,
    calendar as calendar_impl,
    coding as coding_impl,
    docs as docs_impl,
    email as email_impl,
    launcher as launcher_impl,
    medical as medical_impl,
    memory_tools as memory_tools_impl,
    search as search_impl,
    tasks as tasks_impl,
    whatsapp as whatsapp_impl,
)

logger = logging.getLogger("nexus.lc_tools")


# --- Read-Only Tools (No Interrupt / Safe to Repeat) ---

@tool
def search_web(query: str, max_results: int = 5) -> str:
    """Search Google News and DuckDuckGo for live news, real-time facts, cricket scores, and current events.

    Args:
        query: Search keywords or topic (e.g. 'latest AI news', 'IND vs NZ cricket score').
        max_results: Maximum number of search results to retrieve (default 5).
    """
    clean_q = (query or "").strip()
    if not clean_q or clean_q.lower() in {"hello", "hi", "none"}:
        return "What would you like to search for?"
    try:
        res = search_impl.web_search(query=clean_q, max_results=max_results)
        return res.get("spoken") or str(res.get("summary") or res)
    except Exception as e:
        return f"Error searching the web: {e}"


@tool
def calculator(expression: str) -> str:
    """Safely calculate mathematical equations, percentages, square roots, powers, or arithmetic expressions.

    Args:
        expression: Math expression to evaluate (e.g. '450 * 12 + 18% of 5000', 'sqrt(144)').
    """
    try:
        res = calc_impl.calculator(expression=expression)
        return res.get("spoken") or str(res.get("result"))
    except Exception as e:
        return f"Error calculating: {e}"


@tool
def medical_search(medicine_name: str, topic: str = "all") -> str:
    """Look up comprehensive, verified medical information about any medicine, drug, brand, or salt.

    Provides therapeutic indications, dosage guidelines, side effects, precautions, and drug interactions.

    Args:
        medicine_name: Name of the medicine, brand, or salt (e.g. 'Paracetamol', 'Dolo 650', 'Metformin').
        topic: Specific focus: 'all', 'uses', 'dosage', 'side_effects', 'precautions', or 'interactions'.
    """
    clean_m = (medicine_name or "").strip()
    if not clean_m or clean_m.lower() in {"hello", "hi", "none"}:
        return "Please name the medicine or pharmaceutical salt you would like information on."
    try:
        res = medical_impl.medical_search(medicine_name=clean_m, topic=topic)
        return res.get("spoken") or str(res.get("summary") or res)
    except Exception as e:
        return f"Error looking up medicine: {e}"


@tool
def open_app(name: str, query: str = "") -> str:
    """Open desktop applications (Calculator, Notepad, Explorer) or websites (YouTube, WhatsApp, LinkedIn, Spotify, GitHub, Gmail).

    Args:
        name: Name of the application or website (e.g. 'youtube', 'notepad', 'linkedin').
        query: Optional search topic or query (e.g. 'lofi music' for YouTube).
    """
    try:
        res = launcher_impl.open_app(name=name, query=query)
        return res.get("spoken") or f"Opening {name}."
    except Exception as e:
        return f"Error opening application {name}: {e}"


@tool
def run_python_code(code: str) -> str:
    """Execute Python code in an isolated REPL to test algorithms, compute logic, or verify scripts.

    Args:
        code: Python script or snippet to execute.
    """
    try:
        res = coding_impl.run_python_code(code=code)
        return res.get("spoken") or (res.get("output") or "Code executed with no output.")
    except Exception as e:
        return f"Error executing Python code: {e}"


@tool
def add_task(title: str, priority: str = "normal", user_id: str = "guest") -> str:
    """Add a new task or to-do item to the user's task list.

    Args:
        title: Short description or title of the task.
        priority: Task priority level ('low', 'normal', 'high').
        user_id: Bound user identifier.
    """
    clean_t = (title or "").strip()
    if not clean_t:
        return "Task title cannot be blank."
    try:
        res = tasks_impl.add_task(title=clean_t, priority=priority, user_id=user_id)
        return res.get("spoken") or f"Task '{clean_t}' added."
    except Exception as e:
        return f"Error adding task: {e}"


@tool
def list_tasks(status: str = "all", user_id: str = "guest") -> str:
    """List pending, completed, or all tasks on the user's task list.

    Args:
        status: Filter tasks by 'pending', 'completed', or 'all'.
        user_id: Bound user identifier.
    """
    try:
        res = tasks_impl.list_tasks(status=status, user_id=user_id)
        return res.get("spoken") or str(res.get("tasks", []))
    except Exception as e:
        return f"Error listing tasks: {e}"


@tool
def complete_task(task_id: str, user_id: str = "guest") -> str:
    """Mark a task on the task list as completed.

    Args:
        task_id: Identifier or title of the task to complete.
        user_id: Bound user identifier.
    """
    try:
        res = tasks_impl.complete_task(task_id=task_id, user_id=user_id)
        return res.get("spoken") or f"Task '{task_id}' marked as complete."
    except Exception as e:
        return f"Error completing task: {e}"


@tool
def list_events(date: str = "today", user_id: str = "guest") -> str:
    """List calendar events scheduled on a specific date.

    Args:
        date: The date to inspect (e.g. 'today', 'tomorrow', or 'YYYY-MM-DD').
        user_id: Bound user identifier.
    """
    try:
        res = calendar_impl.list_events(date=date, user_id=user_id)
        return res.get("spoken") or str(res.get("events", []))
    except Exception as e:
        return f"Error listing calendar events: {e}"


@tool
def find_free_slot(duration_minutes: int = 30, window: str = "tomorrow", user_id: str = "guest") -> str:
    """Find available free time slots on the user's calendar.

    Args:
        duration_minutes: Required meeting duration in minutes (default 30).
        window: Search timeframe (e.g. 'today', 'tomorrow').
        user_id: Bound user identifier.
    """
    try:
        res = calendar_impl.find_free_slot(duration_minutes=duration_minutes, window=window, user_id=user_id)
        return res.get("spoken") or "No free slot found."
    except Exception as e:
        return f"Error finding free calendar slot: {e}"


@tool
def remember(fact: str, user_id: str = "guest") -> str:
    """Save a user fact or preference into long-term semantic memory.

    Args:
        fact: Fact or preference text to store.
        user_id: Bound user identifier.
    """
    try:
        res = memory_tools_impl.remember(fact=fact, user_id=user_id)
        return res.get("spoken") or f"Remembered: {fact}"
    except Exception as e:
        return f"Error remembering fact: {e}"


@tool
def forget(fact: str, user_id: str = "guest") -> str:
    """Remove a fact or preference from long-term memory.

    Args:
        fact: Fact keyword or statement to remove.
        user_id: Bound user identifier.
    """
    try:
        res = memory_tools_impl.forget(fact=fact, user_id=user_id)
        return res.get("spoken") or f"Forgot: {fact}"
    except Exception as e:
        return f"Error forgetting fact: {e}"


@tool
def search_my_docs(query: str, user_id: str = "guest") -> str:
    """Search personal local notes and document text files.

    Args:
        query: Keyword or question to query within indexed local files.
        user_id: Bound user identifier.
    """
    try:
        res = docs_impl.search_my_docs(query=query, user_id=user_id)
        return res.get("spoken") or str(res.get("results") or "No matching documents found.")
    except Exception as e:
        return f"Error searching documents: {e}"


@tool
def get_current_time(timezone: str = "Asia/Kolkata") -> str:
    """Get the current time, date, day of week, and timezone.

    Args:
        timezone: IANA timezone identifier (default 'Asia/Kolkata').
    """
    try:
        from agent.main import get_current_time as gct
        res = gct(timezone=timezone)
        return res.get("spoken") or f"Current time is {res.get('time')} on {res.get('date')}."
    except Exception as e:
        return f"Error getting current time: {e}"


@tool
def send_whatsapp_message(contact_name: str, message: str = "", phone: str = "") -> str:
    """Search for a contact in WhatsApp Web or Desktop, open their chat, and send a message.

    Args:
        contact_name: Name of the recipient contact (e.g. 'Alex', 'Rahul').
        message: Message body to type and deliver.
        phone: Optional direct phone number with country code.
    """
    clean_c = (contact_name or "").strip()
    if not clean_c or clean_c.lower() in {"hello", "none", "me"}:
        return "Please specify the contact name you want to message on WhatsApp."
    try:
        res = whatsapp_impl.send_whatsapp_message(contact_name=contact_name, message=message, phone=phone)
        return res.get("spoken") or f"Sent WhatsApp message to {contact_name}."
    except Exception as e:
        return f"Error sending WhatsApp message: {e}"


# --- Irreversible Tools (Human-In-The-Loop Interrupt MUST Be First Statement) ---

@tool
def send_email(
    to: str = "",
    description: str = "",
    subject: str = "",
    recipient_name: str = "",
    sender_name: str = "",
    user_id: str = "guest",
) -> str:
    """Send an email from the user's Gmail account. This cannot be undone.

    Args:
        to: Recipient email address or comma-separated list.
        description: Brief description of email content.
        subject: Optional email subject line.
        recipient_name: Optional recipient greeting name.
        sender_name: Optional sender name.
        user_id: Bound user identifier.
    """
    # The pause MUST be the first statement in the tool
    approved = interrupt({
        "action": "send_email",
        "to": to,
        "subject": subject or "Email Message",
        "description": description,
        "prompt": f"Ready to send email to {to} regarding '{subject or description}'. Shall I send it?",
    })
    clean_app = str(approved).strip().lower()
    if clean_app not in {"yes", "true", "approved", "confirm", "confirmed", "send", "proceed"}:
        return "User declined. The email was not sent."

    from agent.tools.email import normalize_spoken_email
    clean_to = normalize_spoken_email(to) if to else ""
    res = email_impl.send_email(
        to=clean_to,
        description=description,
        subject=subject,
        recipient_name=recipient_name,
        sender_name=sender_name,
        user_id=user_id,
    )
    return res.get("spoken") or f"Email sent to {clean_to}."


@tool
def delete_task(task_id: str, user_id: str = "guest") -> str:
    """Permanently delete a task from the user's task list. This cannot be undone.

    Args:
        task_id: Identifier or title of the task to delete.
        user_id: Bound user identifier.
    """
    # The pause MUST be the first statement in the tool
    approved = interrupt({
        "action": "delete_task",
        "task_id": task_id,
        "prompt": f"Are you sure you want me to permanently delete task '{task_id}'?",
    })
    clean_app = str(approved).strip().lower()
    if clean_app not in {"yes", "true", "approved", "confirm", "confirmed", "delete", "proceed"}:
        return "User declined. The task was not deleted."

    res = tasks_impl.delete_task(task_id=task_id, user_id=user_id)
    return res.get("spoken") or f"Task '{task_id}' deleted."


@tool
def create_event(
    title: str,
    start: str,
    end: Optional[str] = None,
    attendees: Optional[List[str]] = None,
    user_id: str = "guest",
) -> str:
    """Schedule and create a meeting or calendar event. This modifies the user's calendar.

    Args:
        title: Title or summary of the meeting.
        start: Start date and time expression (e.g. 'tomorrow 4 PM').
        end: Optional end time.
        attendees: Optional list of attendee email addresses.
        user_id: Bound user identifier.
    """
    # The pause MUST be the first statement in the tool
    approved = interrupt({
        "action": "create_event",
        "title": title,
        "start": start,
        "prompt": f"Ready to schedule '{title}' for {start}. Shall I confirm this booking?",
    })
    clean_app = str(approved).strip().lower()
    if clean_app not in {"yes", "true", "approved", "confirm", "confirmed", "schedule", "proceed"}:
        return "User declined. The event was not scheduled."

    res = calendar_impl.create_event(title=title, start=start, end=end, attendees=attendees, user_id=user_id)
    return res.get("spoken") or f"Event '{title}' scheduled for {start}."


LANGGRAPH_TOOLS = [
    search_web,
    calculator,
    medical_search,
    open_app,
    run_python_code,
    add_task,
    list_tasks,
    complete_task,
    delete_task,
    send_email,
    create_event,
    list_events,
    find_free_slot,
    remember,
    forget,
    search_my_docs,
    get_current_time,
    send_whatsapp_message,
]
