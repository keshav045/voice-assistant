"""WhatsApp Contact Search & Automated Messaging Tool.

Enables the voice assistant to:
1. Launch WhatsApp Web or Desktop
2. Search for any contact by name (e.g., 'Krish') in the chat list
3. Open that contact's chat
4. Type and send the specified message (e.g., 'Hiiii')
"""

import os
import re
import sys
import time
import threading
import urllib.parse
import webbrowser
from typing import Any, Dict, Optional

try:
    import pyautogui
    import pyperclip
    AUTOMATION_AVAILABLE = True
except ImportError:
    AUTOMATION_AVAILABLE = False


def _automate_whatsapp_search_and_send(contact_name: str, message: Optional[str] = None):
    """Background worker to search contact name in WhatsApp Web and send message."""
    if not AUTOMATION_AVAILABLE:
        return

    # Wait for browser to open WhatsApp Web and render chat list
    time.sleep(3.5)

    try:
        # Focus the WhatsApp Web search input box (WhatsApp shortcut: Ctrl + Alt + /)
        pyautogui.hotkey("ctrl", "alt", "/")
        time.sleep(0.6)

        # Clear any existing search text
        pyautogui.hotkey("ctrl", "a")
        pyautogui.press("backspace")
        time.sleep(0.3)

        # Type contact name safely via clipboard (handles spaces, capitals & unicode)
        pyperclip.copy(contact_name)
        pyautogui.hotkey("ctrl", "v")
        time.sleep(1.8)  # Wait for search results to filter

        # Press Enter to select the top contact result and open their chat
        pyautogui.press("enter")
        time.sleep(0.8)

        # If a message was provided, paste and send it
        if message and message.strip():
            pyperclip.copy(message.strip())
            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.4)
            pyautogui.press("enter")

    except Exception as err:
        print(f"[WhatsApp Automation Error]: {err}")


def send_whatsapp_message(
    contact_name: str,
    message: Optional[str] = None,
    phone: Optional[str] = None,
    auto_send: bool = True,
) -> Dict[str, Any]:
    """Open WhatsApp, search for the contact in the list, open their chat, and send message.

    Args:
        contact_name: Name of the contact to find in WhatsApp (e.g., 'Krish', 'Mom', 'Alex').
        message: The message text to send (e.g., 'Hiiii').
        phone: Optional direct phone number if known.
        auto_send: Whether to automatically send the message (True) or just stage it (False).

    Returns:
        dict with execution details and spoken response text.
    """
    clean_name = (contact_name or "").strip()
    clean_msg = (message or "").strip()

    if not clean_name and not phone:
        return {
            "success": False,
            "error": "No contact name or phone number provided.",
            "spoken": "Please specify who you would like to message on WhatsApp.",
        }

    # Case A: Direct phone number is provided (use instant deep-link)
    if phone:
        clean_phone = re.sub(r"[^\d+]", "", phone)
        encoded_msg = urllib.parse.quote_plus(clean_msg) if clean_msg else ""
        url = f"https://web.whatsapp.com/send?phone={clean_phone}" + (f"&text={encoded_msg}" if encoded_msg else "")
        try:
            webbrowser.open_new_tab(url)
            spoken = f"Opening chat with {clean_name or clean_phone} on WhatsApp"
            if clean_msg:
                spoken += f" with message '{clean_msg}' ready."
            else:
                spoken += "."
            return {
                "success": True,
                "contact": clean_name or clean_phone,
                "url": url,
                "message": clean_msg,
                "spoken": spoken,
            }
        except Exception as e:
            return {"success": False, "error": str(e), "spoken": "Could not launch WhatsApp."}

    # Case B: Search contact name in the list via WhatsApp Web automation
    whatsapp_url = "https://web.whatsapp.com"
    try:
        # Launch WhatsApp Web in browser
        webbrowser.open_new_tab(whatsapp_url)

        if AUTOMATION_AVAILABLE:
            # Trigger background keyboard navigation: search contact -> open chat -> send message
            t = threading.Thread(
                target=_automate_whatsapp_search_and_send,
                args=(clean_name, clean_msg if auto_send else None),
                daemon=True,
            )
            t.start()

        if clean_msg:
            spoken_text = f"Opening WhatsApp, finding {clean_name} in your chat list, and sending '{clean_msg}'."
        else:
            spoken_text = f"Opening WhatsApp and finding {clean_name}'s chat for you."

        return {
            "success": True,
            "contact": clean_name,
            "message": clean_msg,
            "action": "search_and_send",
            "spoken": spoken_text,
        }

    except Exception as err:
        return {
            "success": False,
            "error": str(err),
            "spoken": f"Encountered an issue opening WhatsApp for {clean_name}.",
        }

