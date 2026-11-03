"""Email tools — real SMTP sending via Gmail + AI subject/body composer.
Supports single recipients, multiple comma/and-separated recipients, and bulk sending via CSV files.

Setup (one-time):
  1. Go to Google Account > Security > 2-Step Verification > App Passwords
  2. Generate an App Password for "Mail" on "Windows Computer"
  3. Add to .env:
        SENDER_EMAIL=your@gmail.com
        SENDER_APP_PASSWORD=xxxx xxxx xxxx xxxx

Voice usage examples:
  "Send an email to john@example.com about the project deadline"
  "Send email to rahul@gmail.com, priya@gmail.com and amit@yahoo.com saying the meeting is shifted to Friday 3pm"
  "Send an email to contacts.csv saying tomorrow's workshop starts at 10 AM"
  "Send an email from csv with subject Launch and description Ready for release"
"""

from __future__ import annotations

import csv
import logging
import os
import re
import smtplib
import ssl
import time
import uuid
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

logger = logging.getLogger("voice_assistant.email")

# --------------------------------------------------------------------------- #
# SMTP configuration (reads from environment at call time)
# --------------------------------------------------------------------------- #

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def _get_smtp_creds() -> tuple[str, str]:
    """Return (sender_email, app_password) from environment."""
    sender = os.environ.get("SENDER_EMAIL", "").strip()
    password = os.environ.get("SENDER_APP_PASSWORD", "").strip()
    return sender, password


def _smtp_configured() -> bool:
    sender, password = _get_smtp_creds()
    return bool(sender and password)


# --------------------------------------------------------------------------- #
# Contact & CSV Parsing Helpers
# --------------------------------------------------------------------------- #

def _load_contacts_from_csv(csv_path: Optional[str] = None) -> Tuple[List[Dict[str, str]], Optional[str]]:
    """Read recipient contacts from a CSV file.
    
    Accepts CSVs with columns such as:
      - 'email', 'e-mail', 'mail', 'to'
      - 'name', 'full_name', 'first_name', 'contact'
    
    Returns:
      (list_of_contacts, error_message_or_None)
    """
    target_path = (csv_path or "contacts.csv").strip()
    
    # Try current directory or absolute path
    resolved_path = Path(target_path)
    if not resolved_path.is_file():
        # Check workspace root
        resolved_path = Path(os.getcwd()) / target_path
    
    if not resolved_path.is_file():
        return [], f"Could not find CSV file at '{target_path}'. Please make sure the file exists."
    
    contacts: List[Dict[str, str]] = []
    try:
        with open(resolved_path, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                return [], f"The CSV file '{target_path}' is empty."
            
            # Identify email and name column headers
            email_col = None
            name_col = None
            for col in reader.fieldnames:
                col_clean = col.strip().lower()
                if col_clean in ["email", "e-mail", "mail", "recipient", "to", "email_address"]:
                    email_col = col
                elif col_clean in ["name", "full_name", "first_name", "contact", "recipient_name"]:
                    name_col = col
            
            for row in reader:
                # Find email
                raw_email = row.get(email_col, "").strip() if email_col else ""
                if not raw_email:
                    # Scan any column containing an '@'
                    for v in row.values():
                        if v and "@" in v:
                            raw_email = v.strip()
                            break
                
                # Validate email format
                if raw_email and "@" in raw_email:
                    contact_name = row.get(name_col, "").strip() if name_col else ""
                    contacts.append({"email": raw_email, "name": contact_name})
                    
        if not contacts:
            return [], f"No valid email addresses were found in '{target_path}'."
        return contacts, None
    except Exception as e:
        return [], f"Failed to read contacts CSV: {e}"


def _parse_recipients(
    to: Optional[Union[str, List[str]]] = None,
    csv_path: Optional[str] = None,
) -> Tuple[List[Dict[str, str]], Optional[str]]:
    """Parse one or more recipients from strings, lists, or CSV references."""
    to_str = str(to or "").strip()
    
    # Check if CSV mode requested
    is_csv_target = (
        bool(csv_path)
        or to_str.lower().endswith(".csv")
        or to_str.lower() in ["csv", "contacts", "contacts.csv", "team.csv"]
        or "from csv" in to_str.lower()
        or "contacts.csv" in to_str.lower()
    )
    
    if is_csv_target:
        effective_path = csv_path
        if not effective_path and to_str.lower().endswith(".csv"):
            effective_path = to_str
        return _load_contacts_from_csv(effective_path)
    
    # List of recipients provided
    if isinstance(to, (list, tuple)):
        results: List[Dict[str, str]] = []
        for item in to:
            if isinstance(item, dict) and "email" in item:
                results.append({"email": str(item["email"]).strip(), "name": str(item.get("name", "")).strip()})
            else:
                s = str(item).strip()
                matches = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', s)
                for em in matches:
                    results.append({"email": em, "name": ""})
        if not results:
            return [], "No valid email addresses were found in the recipient list."
        return results, None
    
    # String provided — extract all email addresses
    # Handles: "a@x.com, b@y.com and c@z.com" or "John <john@example.com>"
    emails_found = re.findall(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+', to_str)
    if emails_found:
        results = []
        for em in emails_found:
            results.append({"email": em, "name": ""})
        return results, None
    
    # If no email addresses could be parsed
    if not to_str:
        return [], "I need a valid email address or CSV contact list to send the mail."
    return [], f"'{to_str}' is not a valid email address. Please provide a valid email or CSV file."


# --------------------------------------------------------------------------- #
# AI subject + body composer (uses OpenAI synchronously — light call)
# --------------------------------------------------------------------------- #

def _compose_email(description: str, recipient_name: str = "") -> Dict[str, str]:
    """Use OpenAI to generate a professional subject and body from a brief description.
    Falls back to a simple template if the API key is missing.
    """
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key or api_key.startswith("your-"):
        subject = f"Message{' for ' + recipient_name if recipient_name else ''}"
        body = description
        return {"subject": subject, "body": body}

    try:
        from openai import OpenAI  # synchronous client
        client = OpenAI(api_key=api_key)

        prompt = f"""You are a professional email assistant.
A user wants to send an email. Their description is:
"{description}"

{"Recipient name: " + recipient_name if recipient_name else ""}

Generate a concise, professional email.
Respond ONLY with valid JSON in this exact format (no markdown, no extra text):
{{
  "subject": "<email subject line>",
  "body": "<full email body with greeting and sign-off>"
}}"""

        response = client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=400,
        )

        import json
        raw = (response.choices[0].message.content or "").strip()
        raw = raw.strip("```json").strip("```").strip()
        result = json.loads(raw)
        return {
            "subject": result.get("subject", "No Subject"),
            "body": result.get("body", description),
        }
    except Exception as e:
        logger.warning(f"AI compose failed, using fallback: {e}")
        return {
            "subject": f"Message{' for ' + recipient_name if recipient_name else ''}",
            "body": description,
        }


# --------------------------------------------------------------------------- #
# Core sending function (Single recipient dispatch)
# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
# Core sending functions: Gmail REST API (OAuth) & SMTP Fallback
# --------------------------------------------------------------------------- #

def _send_gmail_api(to_email: str, subject: str, body: str, access_token: str, sender_email: str) -> Dict[str, Any]:
    """Send an email using official Google Gmail REST API (users.messages.send)."""
    import base64
    import httpx

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = to_email

    # Plain-text and HTML versions
    msg.attach(MIMEText(body, "plain", "utf-8"))
    html_body = f"<html><body><p>{body.replace(chr(10), '<br>')}</p></body></html>"
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    raw_bytes = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

    url = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    payload = {"raw": raw_bytes}

    try:
        response = httpx.post(url, headers=headers, json=payload, timeout=20.0)
        if response.status_code == 200:
            logger.info(f"Gmail REST API: Email sent to {to_email} | subject: {subject}")
            return {"success": True, "to": to_email, "subject": subject}
        else:
            err_msg = response.text
            try:
                err_data = response.json()
                err_msg = err_data.get("error", {}).get("message", response.text)
            except Exception:
                pass
            logger.error(f"Gmail REST API error: {err_msg}")
            return {"success": False, "error": err_msg, "spoken": f"Gmail API error: {err_msg}"}
    except Exception as e:
        logger.error(f"Gmail REST API request failed: {e}")
        return {"success": False, "error": str(e), "spoken": f"Gmail delivery failed: {e}"}


def _get_fresh_google_access_token(user_id: str) -> Optional[Tuple[str, str]]:
    """Retrieve fresh Google access token using stored refresh token.
    Returns (access_token, user_email) or None.
    """
    from db.models import db_get_user_oauth, db_save_user_oauth
    import httpx

    record = db_get_user_oauth(user_id=user_id, provider="google")
    if not record:
        return None

    client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
    refresh_token = record.get("refresh_token")
    user_email = record.get("email") or ""
    current_token = record.get("access_token")

    # If we have refresh credentials, refresh access token
    if client_id and client_secret and refresh_token:
        try:
            token_url = "https://oauth2.googleapis.com/token"
            resp = httpx.post(
                token_url,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
                timeout=10.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                fresh_access_token = data.get("access_token")
                if fresh_access_token:
                    db_save_user_oauth(
                        user_id=user_id,
                        email=user_email,
                        access_token=fresh_access_token,
                        refresh_token=refresh_token,
                    )
                    return fresh_access_token, user_email
        except Exception as e:
            logger.warning(f"Could not refresh Google token: {e}")

    if current_token:
        return current_token, user_email
    return None


def _send_smtp(to_email: str, subject: str, body: str) -> Dict[str, Any]:
    """Send email via Gmail SMTP. Tries port 587 (STARTTLS) then 465 (SSL)."""
    sender_email, app_password = _get_smtp_creds()

    if not sender_email or not app_password:
        return {
            "success": False,
            "error": "SMTP not configured",
            "spoken": (
                "Email is not configured yet. Please open the dot-env file, "
                "set SENDER_EMAIL to your Gmail address, and set SENDER_APP_PASSWORD "
                "to a 16-character Gmail App Password."
            ),
        }

    clean_password = app_password.replace(" ", "")
    if len(clean_password) != 16:
        return {
            "success": False,
            "error": f"App password has {len(clean_password)} chars, expected 16.",
            "spoken": (
                f"The Gmail App Password in your dot-env file looks incorrect — "
                f"it has {len(clean_password)} characters but should be exactly 16."
            ),
        }

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = sender_email
    msg["To"] = to_email

    # Plain-text part
    msg.attach(MIMEText(body, "plain", "utf-8"))

    # HTML part
    html_body = f"<html><body><p>{body.replace(chr(10), '<br>')}</p></body></html>"
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    context = ssl.create_default_context()

    def _try_587() -> None:
        with smtplib.SMTP(SMTP_HOST, 587, timeout=15) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(sender_email, clean_password)
            server.sendmail(sender_email, to_email, msg.as_string())

    def _try_465() -> None:
        with smtplib.SMTP_SSL(SMTP_HOST, 465, context=context, timeout=15) as server:
            server.ehlo()
            server.login(sender_email, clean_password)
            server.sendmail(sender_email, to_email, msg.as_string())

    last_err: Exception | None = None
    for attempt in (_try_587, _try_465):
        try:
            attempt()
            logger.info(f"Email sent to {to_email} | subject: {subject}")
            return {"success": True, "to": to_email, "subject": subject}
        except smtplib.SMTPAuthenticationError:
            return {
                "success": False,
                "error": "Authentication failed",
                "spoken": "Gmail authentication failed. Please verify your SENDER_APP_PASSWORD.",
            }
        except Exception as e:
            last_err = e
            logger.warning(f"SMTP attempt failed ({attempt.__name__}): {e}")
            continue

    return {
        "success": False,
        "error": str(last_err),
        "spoken": f"Could not send email to {to_email}: {last_err}",
    }


# --------------------------------------------------------------------------- #
# Public tool: send_email — Single, Multi-Recipient & Bulk CSV
# --------------------------------------------------------------------------- #

def send_email(
    to: Optional[Union[str, List[str]]] = None,
    description: Optional[str] = None,
    subject: Optional[str] = None,
    body: Optional[str] = None,
    recipient_name: Optional[str] = None,
    csv_path: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Compose and send emails to a single recipient, multiple recipients, or bulk contacts via CSV.

    Uses the user's connected Google Account (via Gmail REST API) if linked,
    or falls back to Gmail SMTP credentials from .env.
    """
    effective_user_id = user_id or "guest"

    # 1. Parse Recipients (single, multi, or CSV)
    recipients, parse_err = _parse_recipients(to=to, csv_path=csv_path)
    if parse_err or not recipients:
        spoken_msg = parse_err if parse_err and "csv" in parse_err.lower() else "I need a valid email address to send the mail. Could you provide the recipient's email?"
        return {
            "success": False,
            "error": parse_err or "No valid recipients found",
            "spoken": spoken_msg,
        }

    # 2. Validate Description / Content
    if not description and not (subject and body):
        return {
            "success": False,
            "spoken": "Please describe what you want to say in the email.",
        }

    # 3. Determine Subject & Base Body
    if subject and body:
        final_subject = subject
        base_body = body
    elif description:
        composed = _compose_email(description, recipient_name or "")
        final_subject = subject or composed["subject"]
        base_body = body or composed["body"]
    else:
        return {
            "success": False,
            "spoken": "Please describe what you want to say in the email.",
        }

    # Internal dispatcher: checks Google OAuth first, then SMTP
    def _deliver(to_em: str, subj: str, bdy: str) -> Dict[str, Any]:
        token_info = _get_fresh_google_access_token(user_id=effective_user_id) if effective_user_id else None
        if token_info:
            access_tok, sender_em = token_info
            return _send_gmail_api(to_email=to_em, subject=subj, body=bdy, access_token=access_tok, sender_email=sender_em)
        return _send_smtp(to_email=to_em, subject=subj, body=bdy)

    # ----------------------------------------------------------------------- #
    # Case A: Single Recipient
    # ----------------------------------------------------------------------- #
    if len(recipients) == 1:
        target_email = recipients[0]["email"]
        target_name = recipient_name or recipients[0]["name"]
        
        result = _deliver(to_em=target_email, subj=final_subject, bdy=base_body)
        if result["success"]:
            name_part = f" to {target_name}" if target_name else f" to {target_email}"
            result["spoken"] = (
                f"Done! I've sent the email{name_part} with the subject \"{final_subject}\"."
            )
            result["subject"] = final_subject
            result["body"] = base_body
            result["to"] = target_email
        return result

    # ----------------------------------------------------------------------- #
    # Case B: Multiple / Bulk Recipients (via Commas, 'and', or CSV)
    # ----------------------------------------------------------------------- #
    successful: List[str] = []
    failed: List[Dict[str, str]] = []

    for idx, r in enumerate(recipients):
        em = r["email"]
        nm = r["name"]
        
        # Personalized greeting if name available
        recipient_body = base_body
        if nm and ("Dear" in base_body or "Hi" in base_body or "Hello" in base_body):
            recipient_body = re.sub(r'^(Dear|Hi|Hello)\s+[A-Za-z]+,', f'\\1 {nm},', base_body, flags=re.MULTILINE)

        send_res = _deliver(to_em=em, subj=final_subject, bdy=recipient_body)
        if send_res.get("success"):
            successful.append(em)
        else:
            failed.append({"email": em, "error": send_res.get("error", "Failed")})

        if idx < len(recipients) - 1:
            time.sleep(0.3)

    total_count = len(recipients)
    success_count = len(successful)
    is_overall_success = success_count > 0

    if success_count == total_count:
        if total_count <= 3:
            recip_list = ", ".join(successful)
            spoken = f"Done! Successfully sent all {total_count} emails to {recip_list} with the subject \"{final_subject}\"."
        else:
            spoken = f"Done! Successfully sent all {total_count} emails to your contacts with the subject \"{final_subject}\"."
    elif success_count > 0:
        failed_list = ", ".join([f["email"] for f in failed])
        spoken = (
            f"Sent {success_count} of {total_count} emails successfully with subject \"{final_subject}\". "
            f"Failed for: {failed_list}."
        )
    else:
        spoken = f"Failed to deliver emails to all {total_count} recipients. Please check your Gmail connection."

    return {
        "success": is_overall_success,
        "total": total_count,
        "sent_count": success_count,
        "failed_count": len(failed),
        "recipients": successful,
        "failed": failed,
        "subject": final_subject,
        "body": base_body,
        "spoken": spoken,
    }


# --------------------------------------------------------------------------- #
# Legacy stub functions (retained for test compatibility)
# --------------------------------------------------------------------------- #

_SAMPLE_EMAILS: Dict[str, Dict[str, Any]] = {
    "msg-1": {
        "id": "msg-1",
        "sender": "sarah.chen@company.com",
        "subject": "Launch blockers for v2.4",
        "snippet": "Database migration completed cleanly.",
        "date": "Today, 08:30 AM",
        "unread": True,
    },
}

_DRAFTS_STORE: Dict[str, Dict[str, Any]] = {}


def search_email(query: str = "") -> Dict[str, Any]:
    """Search inbox stub."""
    q = query.lower()
    matches = [
        m for m in _SAMPLE_EMAILS.values()
        if not q or q in m["subject"].lower() or q in m["snippet"].lower() or q in m["sender"].lower()
    ]
    if not matches:
        return {"success": True, "count": 0, "emails": [], "spoken": f"No emails found matching '{query}'."}
    spoken = f"Found {len(matches)} email. The latest is from {matches[0]['sender']} about {matches[0]['subject']}."
    return {"success": True, "count": len(matches), "emails": matches, "spoken": spoken}


def summarize_email(id: Optional[str] = None) -> Dict[str, Any]:
    """Summarise email stub."""
    email = _SAMPLE_EMAILS.get(id or "msg-1") or next(iter(_SAMPLE_EMAILS.values()), None)
    if not email:
        return {"success": False, "spoken": f"Could not find an email matching '{id}'."}
    spoken = f"Email from {email['sender']} regarding {email['subject']}: {email['snippet']}"
    return {"success": True, "email": email, "spoken": spoken}


def draft_reply(
    id: Optional[str] = None,
    points: Optional[str] = None,
    to: Optional[str] = None,
    subject: Optional[str] = None,
    body: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a draft without sending."""
    draft_id = f"draft-{uuid.uuid4().hex[:6]}"
    target_to = to or id or "recipient@example.com"
    content = body or points or "Thank you for the update."
    draft = {
        "id": draft_id,
        "reply_to": target_to,
        "subject": subject or "Re: Update",
        "body": content,
        "status": "draft",
    }
    _DRAFTS_STORE[draft_id] = draft
    return {
        "success": True,
        "draft_id": draft_id,
        "draft": draft,
        "spoken": f"Created a draft reply to {target_to}.",
    }
