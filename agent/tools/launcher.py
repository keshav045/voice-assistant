"""App and Website Launcher tool for Personal Voice Assistant.

Enables opening websites and desktop applications on the laptop.
If an application is not installed natively, it automatically falls back
to opening the web version in Chrome, Microsoft Edge, or the default browser.
"""

import os
import subprocess
import sys
import urllib.parse
import webbrowser
from typing import Any, Dict, Optional


APP_SITES: Dict[str, Dict[str, Any]] = {
    "youtube": {
        "display": "YouTube",
        "url": "https://www.youtube.com",
        "search_url": "https://www.youtube.com/results?search_query={query}",
        "spoken": "Opening YouTube",
    },
    "whatsapp": {
        "display": "WhatsApp",
        "url": "https://web.whatsapp.com",
        "windows_cmd": "WhatsApp.exe",
        "spoken": "Opening WhatsApp",
    },
    "mail": {
        "display": "Gmail",
        "url": "https://mail.google.com",
        "spoken": "Opening your email inbox",
    },
    "gmail": {
        "display": "Gmail",
        "url": "https://mail.google.com",
        "spoken": "Opening Gmail",
    },
    "email": {
        "display": "Email",
        "url": "https://mail.google.com",
        "spoken": "Opening your email inbox",
    },
    "linkedin": {
        "display": "LinkedIn",
        "url": "https://www.linkedin.com",
        "search_url": "https://www.linkedin.com/search/results/all/?keywords={query}",
        "spoken": "Opening LinkedIn",
    },
    "github": {
        "display": "GitHub",
        "url": "https://github.com",
        "search_url": "https://github.com/search?q={query}",
        "spoken": "Opening GitHub",
    },
    "google": {
        "display": "Google",
        "url": "https://www.google.com",
        "search_url": "https://www.google.com/search?q={query}",
        "spoken": "Opening Google",
    },
    "twitter": {
        "display": "X (Twitter)",
        "url": "https://x.com",
        "spoken": "Opening X",
    },
    "x": {
        "display": "X (Twitter)",
        "url": "https://x.com",
        "spoken": "Opening X",
    },
    "spotify": {
        "display": "Spotify",
        "url": "https://open.spotify.com",
        "windows_cmd": "Spotify.exe",
        "spoken": "Opening Spotify",
    },
    "calculator": {
        "display": "Calculator",
        "windows_cmd": "calc.exe",
        "url": "https://www.google.com/search?q=calculator",
        "spoken": "Opening Calculator",
    },
    "notepad": {
        "display": "Notepad",
        "windows_cmd": "notepad.exe",
        "url": "https://keep.google.com",
        "spoken": "Opening Notepad",
    },
    "explorer": {
        "display": "File Explorer",
        "windows_cmd": "explorer.exe",
        "spoken": "Opening File Explorer",
    },
    "files": {
        "display": "File Explorer",
        "windows_cmd": "explorer.exe",
        "spoken": "Opening File Explorer",
    },
    "notion": {
        "display": "Notion",
        "url": "https://www.notion.so",
        "windows_cmd": "Notion.exe",
        "spoken": "Opening Notion",
    },
    "slack": {
        "display": "Slack",
        "url": "https://app.slack.com",
        "windows_cmd": "slack.exe",
        "spoken": "Opening Slack",
    },
    "discord": {
        "display": "Discord",
        "url": "https://discord.com/app",
        "windows_cmd": "Discord.exe",
        "spoken": "Opening Discord",
    },
    "telegram": {
        "display": "Telegram",
        "url": "https://web.telegram.org",
        "windows_cmd": "Telegram.exe",
        "spoken": "Opening Telegram",
    },
}


def launch_in_browser(url: str, browser: Optional[str] = None) -> bool:
    """Launch a URL in Chrome, Microsoft Edge, or the default system browser."""
    b_clean = (browser or "").strip().lower()

    # Try Google Chrome
    if "chrome" in b_clean and sys.platform.startswith("win"):
        for path in [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        ]:
            if os.path.exists(path):
                try:
                    subprocess.Popen([path, url])
                    return True
                except Exception:
                    pass

    # Try Microsoft Edge
    if "edge" in b_clean and sys.platform.startswith("win"):
        for path in [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]:
            if os.path.exists(path):
                try:
                    subprocess.Popen([path, url])
                    return True
                except Exception:
                    pass
        try:
            if hasattr(os, "startfile"):
                os.startfile(f"microsoft-edge:{url}")
                return True
        except Exception:
            pass

    # Default browser
    try:
        webbrowser.open_new_tab(url)
        return True
    except Exception:
        return False


def is_windows_app_installed(cmd: str) -> bool:
    """Check if a Windows executable is accessible on the system."""
    if not sys.platform.startswith("win"):
        return False
    # Standard tools in system32
    if cmd in ["calc.exe", "notepad.exe", "explorer.exe"]:
        return True
    # Try finding in PATH
    import shutil
    if shutil.which(cmd):
        return True
    # Common app locations in LocalAppData
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    for base in [local_app_data, program_files, program_files_x86]:
        if base and os.path.exists(base):
            for root, dirs, files in os.walk(base):
                if cmd.lower() in [f.lower() for f in files]:
                    return True
                # Limit depth
                if root.count(os.sep) - base.count(os.sep) >= 2:
                    break
    return False


def open_app(
    name: str,
    query: Optional[str] = None,
    url: Optional[str] = None,
    browser: Optional[str] = None,
) -> Dict[str, Any]:
    """Launch a website or application on the laptop.

    If a native desktop app is not installed, it automatically falls back
    to opening the web app in Chrome, Microsoft Edge, or the default browser.

    Args:
        name: Name of the application or website (e.g. 'youtube', 'whatsapp', 'mail', 'linkedin').
        query: Optional search topic or query (e.g. 'lofi beats' on YouTube).
        url: Direct custom URL to open if specified.
        browser: Optional preferred browser e.g. 'chrome', 'edge', or 'default'.

    Returns:
        dict with execution status, target, URL or method, and spoken text.
    """
    clean_name = (name or "").strip().lower()
    clean_query = (query or "").strip()
    browser_pref = (browser or "").strip().lower()

    # Direct URL provided
    if url or clean_name.startswith("http://") or clean_name.startswith("https://"):
        target_url = url or clean_name
        success = launch_in_browser(target_url, browser_pref)
        b_label = f" in {browser_pref.capitalize()}" if browser_pref in ["chrome", "edge"] else ""
        return {
            "success": success,
            "target": clean_name,
            "url": target_url,
            "browser": browser_pref or "default",
            "spoken": f"Opening {target_url}{b_label}.",
        }

    # Match predefined app or website
    matched_key = None
    for k in APP_SITES:
        if k == clean_name or k in clean_name or clean_name in k:
            matched_key = k
            break

    if not matched_key:
        # Fallback to web search
        if "." in clean_name and " " not in clean_name:
            target_url = f"https://{clean_name}"
        else:
            encoded = urllib.parse.quote_plus(clean_query or clean_name)
            target_url = f"https://www.google.com/search?q={encoded}"
        success = launch_in_browser(target_url, browser_pref)
        return {
            "success": success,
            "target": clean_name,
            "url": target_url,
            "browser": browser_pref or "default",
            "spoken": f"Opening {clean_name}.",
        }

    app_info = APP_SITES[matched_key]
    display = app_info["display"]
    spoken_base = app_info.get("spoken", f"Opening {display}")
    b_label = f" in {browser_pref.capitalize()}" if browser_pref in ["chrome", "edge"] else ""

    windows_cmd = app_info.get("windows_cmd")
    web_fallback_url = app_info.get("url")

    # If user explicitly requested a web browser (e.g. "in Chrome" or "in Edge" or "in browser")
    # or if there's a search query: prioritize browser
    user_wants_browser = bool(browser_pref or clean_query or not windows_cmd)

    if not user_wants_browser and windows_cmd and sys.platform.startswith("win"):
        # Check if desktop application exists
        if is_windows_app_installed(windows_cmd):
            try:
                subprocess.Popen(windows_cmd, shell=True)
                return {
                    "success": True,
                    "target": display,
                    "action": "desktop_app",
                    "spoken": f"{spoken_base} for you.",
                }
            except Exception:
                # Fall back to browser below
                pass
        # If desktop app is not installed or failed, fall back to browser!
        if web_fallback_url:
            launch_in_browser(web_fallback_url, browser_pref)
            return {
                "success": True,
                "target": display,
                "url": web_fallback_url,
                "fallback_to_browser": True,
                "browser": browser_pref or "default",
                "spoken": f"{display} desktop app is not installed, so I've opened {display} Web in your browser.",
            }

    # Build web URL
    if clean_query and "search_url" in app_info:
        encoded_q = urllib.parse.quote_plus(clean_query)
        target_url = app_info["search_url"].format(query=encoded_q)
        spoken_msg = f"{spoken_base} and searching for '{clean_query}'{b_label}."
    else:
        target_url = web_fallback_url or f"https://{matched_key}.com"
        spoken_msg = f"{spoken_base}{b_label} for you."

    success = launch_in_browser(target_url, browser_pref)
    return {
        "success": success,
        "target": display,
        "url": target_url,
        "browser": browser_pref or "default",
        "spoken": spoken_msg,
    }
