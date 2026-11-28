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
except (ImportError, Exception):
    AUTOMATION_AVAILABLE = False


def _automate_whatsapp_search_and_send(contact_name: str, message: Optional[str] = None):
    """Background worker to search contact name in WhatsApp Web and send message."""
    if not AUTOMATION_AVAILABLE:
        return

    # Safely disable fail-safe for background worker to avoid corner cursor aborts
    try:
        pyautogui.FAILSAFE = False
    except Exception:
        pass

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
    contact_name: Optional[str] = None,
    message: Optional[str] = None,
    phone: Optional[str] = None,
    auto_send: bool = True,
    launch_browser: bool = True,
) -> Dict[str, Any]:
    """Open WhatsApp, search for the contact in the list, open their chat, and send message."""
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
            if launch_browser:
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

    # Case B: Search contact name in the list via WhatsApp Web
    whatsapp_url = "https://web.whatsapp.com"
    try:
        if launch_browser:
            webbrowser.open_new_tab(whatsapp_url)

        desktop_automation_allowed = (
            AUTOMATION_AVAILABLE
            and auto_send
            and bool(clean_msg)
            and "PYTEST_CURRENT_TEST" not in os.environ
            and os.environ.get("NEXUS_DISABLE_DESKTOP_SIDE_EFFECTS") != "1"
        )
        if desktop_automation_allowed:
            t = threading.Thread(
                target=_automate_whatsapp_search_and_send,
                args=(clean_name, clean_msg),
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
            "url": whatsapp_url,
            "message": clean_msg,
            "action": "search_and_send" if clean_msg else "open_chat",
            "spoken": spoken_text,
        }

    except Exception as err:
        return {
            "success": False,
            "error": str(err),
            "spoken": f"Encountered an issue opening WhatsApp for {clean_name}.",
        }

