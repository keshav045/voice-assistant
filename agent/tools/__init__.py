"""Tools catalog and dispatcher for Personal Voice Assistant."""

from typing import Any, Callable, Dict, List
from agent.tools.search import web_search, get_current_time
from agent.tools.calendar import list_events, find_free_slot, create_event
from agent.tools.email import search_email, summarize_email, draft_reply, send_email  # send_email does real SMTP
from agent.tools.tasks import add_task, list_tasks, complete_task
from agent.tools.docs import search_my_docs
from agent.tools.memory_tools import remember, forget
from agent.tools.calc import calculator
from agent.tools.coding import run_python_code
from agent.tools.launcher import open_app
from agent.tools.whatsapp import send_whatsapp_message

TOOLS_REGISTRY: Dict[str, Callable[..., Any]] = {
    "web_search": web_search,
    "get_current_time": get_current_time,
    "calculator": calculator,
    "run_python_code": run_python_code,
    "open_app": open_app,
    "send_whatsapp_message": send_whatsapp_message,
    "list_events": list_events,
    "find_free_slot": find_free_slot,
    "create_event": create_event,
    "add_task": add_task,
    "list_tasks": list_tasks,
    "complete_task": complete_task,
    "search_email": search_email,
    "summarize_email": summarize_email,
    "draft_reply": draft_reply,
    "send_email": send_email,
    "search_my_docs": search_my_docs,
    "remember": remember,
    "forget": forget,
}

CONFIRMATION_REQUIRED_TOOLS = {"create_event", "send_email"}

TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "send_whatsapp_message",
            "description": "Find a contact by name in WhatsApp, open their chat, and send or type a message. Use this whenever the user asks to message someone on WhatsApp or open a specific person's chat (e.g. 'open whatsapp, open Krish's chat and message him Hiiii').",
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_name": {
                        "type": "string",
                        "description": "The name of the contact or group to find in WhatsApp, e.g. 'Krish', 'Mom', 'Alex'.",
                    },
                    "message": {
                        "type": "string",
                        "description": "The text message to send to the contact, e.g. 'Hiiii', 'Good morning'.",
                    },
                    "phone": {
                        "type": "string",
                        "description": "Optional direct phone number if specified.",
                    },
                },
                "required": ["contact_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_app",
            "description": "Open websites or applications on the laptop, such as YouTube, WhatsApp, Gmail/Mail, LinkedIn, GitHub, Google, Spotify, Calculator, Notepad, etc. Can also search for videos on YouTube or topics on LinkedIn (e.g. 'open youtube and search for crazy xyz new video'). Use this whenever the user asks to open an app or search/play on YouTube, NOT web_search.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "The name of the website or application, e.g. 'youtube', 'whatsapp', 'mail', 'gmail', 'linkedin', 'github', 'spotify', 'calculator', 'notepad'.",
                    },
                    "query": {
                        "type": "string",
                        "description": "Optional search query, video title, or topic to search for on the platform (e.g. 'crazy xyz new video', 'lofi music').",
                    },
                    "url": {
                        "type": "string",
                        "description": "Optional direct URL to navigate to.",
                    },
                    "browser": {
                        "type": "string",
                        "description": "Optional browser to open the website in, e.g. 'chrome', 'edge', or 'default'.",
                        "enum": ["chrome", "edge", "default"],
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for real-time information, latest news headlines, live cricket scores, sports match scorecards, current events, and up-to-date facts. Do NOT call this when the user asks to open or search inside YouTube, WhatsApp, or specific applications (use open_app instead).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query string"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "Evaluate mathematical expressions, arithmetic, percentages, powers, square roots, and math formulas safely. E.g. '15% of 2340', 'sqrt(144) + 2**8'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "The math expression to evaluate"},
                },
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_python_code",
            "description": "Execute basic Python code to demonstrate coding solutions, test algorithms, perform logical reasoning, or compute complex results. Returns stdout.",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "The Python source code to execute"},
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Get current time, day, and date in the user's timezone (default Asia/Kolkata).",
            "parameters": {
                "type": "object",
                "properties": {
                    "timezone_str": {"type": "string", "description": "Optional timezone identifier e.g. Asia/Kolkata"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_events",
            "description": "Read calendar events and meetings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start": {"type": "string", "description": "Start date/time"},
                    "end": {"type": "string", "description": "End date/time"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_free_slot",
            "description": "Suggest open meeting slots without conflict.",
            "parameters": {
                "type": "object",
                "properties": {
                    "duration_minutes": {"type": "integer", "description": "Meeting length in minutes"},
                    "window": {"type": "string", "description": "Time window e.g. today, tomorrow"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_event",
            "description": "Create a calendar entry. Needs confirmation read-back.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Event title"},
                    "start": {"type": "string", "description": "Start date/time e.g. 2026-11-01T16:00:00"},
                    "end": {"type": "string", "description": "End date/time"},
                    "attendees": {"type": "array", "items": {"type": "string"}, "description": "List of attendee emails"},
                },
                "required": ["title", "start"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_task",
            "description": "Add a task or to-do item to the task database.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Actionable task title"},
                    "due_date": {"type": "string", "description": "Optional due date"},
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_tasks",
            "description": "List tasks from database by status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["pending", "completed"], "description": "Status filter"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "complete_task",
            "description": "Mark a task complete by ID or name keyword.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Task ID or search keyword"},
                },
                "required": ["id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_email",
            "description": "Search inbox for emails matching query or sender.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Keywords or sender name"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "summarize_email",
            "description": "Provide a concise spoken summary of an email message.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Email ID or sender keyword"},
                },
                "required": ["id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "draft_reply",
            "description": "Draft an email reply without sending it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Email ID being replied to"},
                    "points": {"type": "string", "description": "Key points to include in draft"},
                },
                "required": ["id", "points"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_email",
            "description": (
                "Compose and send single or bulk emails via Gmail. "
                "Supports multiple recipients separated by commas or 'and', as well as bulk mailing via a CSV contacts file (e.g. 'contacts.csv'). "
                "The AI will auto-generate a professional subject and body from the user's plain-language description. "
                "Examples: "
                "'send an email to priya@gmail.com saying the meeting is shifted to Friday', "
                "'send email to rahul@gmail.com, priya@gmail.com and amit@yahoo.com saying the workshop starts at 10 AM', "
                "'send email to contacts.csv saying project updates are ready'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {
                        "type": "string",
                        "description": "Recipient email address, multiple comma/and-separated emails (e.g. 'a@x.com, b@y.com and c@z.com'), or 'contacts.csv' / 'csv'.",
                    },
                    "description": {
                        "type": "string",
                        "description": (
                            "Plain-language description of what to say in the email. "
                            "The AI will turn this into a polished subject and body. "
                            "E.g. 'tell them the meeting is moved to Friday 3pm'."
                        ),
                    },
                    "csv_path": {
                        "type": "string",
                        "description": "Optional explicit path to contacts CSV file (defaults to 'contacts.csv' if sending in bulk from file).",
                    },
                    "recipient_name": {
                        "type": "string",
                        "description": "Optional name of the recipient used to personalise the greeting, e.g. 'Priya'.",
                    },
                    "subject": {
                        "type": "string",
                        "description": "Optional explicit subject line (overrides AI generation).",
                    },
                    "body": {
                        "type": "string",
                        "description": "Optional explicit email body (overrides AI generation).",
                    },
                },
                "required": ["to", "description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_my_docs",
            "description": "Search personal indexed documents and notes (RAG) with source citations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Topic or question to search across documents"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remember",
            "description": "Store a user fact or preference in long-term memory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "fact": {"type": "string", "description": "Fact or preference to remember"},
                    "category": {"type": "string", "description": "Optional category e.g. preference, contact, schedule"},
                },
                "required": ["fact"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "forget",
            "description": "Remove a fact or preference from memory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "fact": {"type": "string", "description": "Fact keyword to forget"},
                },
                "required": ["fact"],
            },
        },
    },
]

