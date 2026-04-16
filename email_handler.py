"""
email_handler.py — Gmail send integration for DocAnalyser.

Handles OAuth 2.0 authentication (reusing the existing gdrive_credentials.json)
and sending HTML digest emails via the Gmail API.

Contacts are persisted to:
    %APPDATA%\\DocAnalyser_Beta\\gmail_contacts.json

Token is saved to:
    %APPDATA%\\DocAnalyser_Beta\\gmail_token.json

On first use, a browser window opens for OAuth authorisation.
Subsequent sends use the saved/refreshed token silently.
"""

from __future__ import annotations

import json
import logging
import os
import re
import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# Gmail send scope only — keep separate from Drive token so scope sets
# don't collide if the user authorises them at different times.
GMAIL_SCOPES = ['https://www.googleapis.com/auth/gmail.send']

# ─────────────────────────────────────────────────────────────────────────────
# Optional dependency guard
# ─────────────────────────────────────────────────────────────────────────────
try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    GMAIL_AVAILABLE = True
except ImportError:
    GMAIL_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────────────────
# Markdown → HTML converter
# ─────────────────────────────────────────────────────────────────────────────

def markdown_to_html(text: str) -> str:
    """
    Convert DocAnalyser markdown output to clean inline-styled HTML
    suitable for email (Gmail, Outlook, Yahoo etc).

    Handles:
        # H1 headings
        ## H2 headings
        ### H3 headings
        **bold**
        *italic*  or  _italic_
        Blank-line-separated paragraphs
        Horizontal rules (--- or ===)
    """
    # Styles (inline — email clients strip <style> blocks)
    H1  = 'font-family:Arial,sans-serif;font-size:22px;font-weight:bold;color:#1a1a2e;margin:24px 0 8px 0;border-bottom:2px solid #4a9eff;padding-bottom:4px;'
    H2  = 'font-family:Arial,sans-serif;font-size:17px;font-weight:bold;color:#1a1a2e;margin:20px 0 6px 0;'
    H3  = 'font-family:Arial,sans-serif;font-size:14px;font-weight:bold;color:#333;margin:16px 0 4px 0;'
    P   = 'font-family:Arial,sans-serif;font-size:14px;line-height:1.7;color:#333;margin:0 0 12px 0;'
    HR  = 'border:none;border-top:1px solid #ddd;margin:20px 0;'

    lines  = text.split('\n')
    blocks : List[str] = []
    para_lines: List[str] = []

    def flush_para():
        joined = ' '.join(para_lines).strip()
        if joined:
            blocks.append(f'<p style="{P}">{joined}</p>')
        para_lines.clear()

    for raw in lines:
        line = raw.rstrip()

        # Horizontal rule
        if re.match(r'^[-=]{3,}\s*$', line):
            flush_para()
            blocks.append(f'<hr style="{HR}">')
            continue

        # Headings
        h3 = re.match(r'^###\s+(.*)', line)
        h2 = re.match(r'^##\s+(.*)',  line)
        h1 = re.match(r'^#\s+(.*)',   line)
        if h1:
            flush_para()
            blocks.append(f'<h1 style="{H1}">{_inline(h1.group(1))}</h1>')
            continue
        if h2:
            flush_para()
            blocks.append(f'<h2 style="{H2}">{_inline(h2.group(1))}</h2>')
            continue
        if h3:
            flush_para()
            blocks.append(f'<h3 style="{H3}">{_inline(h3.group(1))}</h3>')
            continue

        # Blank line → flush paragraph
        if not line:
            flush_para()
            continue

        # Accumulate paragraph text
        para_lines.append(_inline(line))

    flush_para()

    body_html = '\n'.join(blocks)

    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f5f5f5;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f5;padding:20px 0;">
    <tr><td align="center">
      <table width="640" cellpadding="0" cellspacing="0"
             style="background:#ffffff;border-radius:6px;
                    box-shadow:0 2px 8px rgba(0,0,0,0.08);
                    padding:32px 40px;max-width:640px;">
        <tr><td>
          <!-- Header banner -->
          <table width="100%" cellpadding="0" cellspacing="0"
                 style="background:#1a1a2e;border-radius:4px;
                        margin-bottom:28px;padding:16px 24px;">
            <tr>
              <td style="font-family:Arial,sans-serif;font-size:13px;
                         font-weight:bold;color:#4a9eff;
                         letter-spacing:2px;text-transform:uppercase;">
                DocAnalyser Intelligence
              </td>
              <td align="right"
                  style="font-family:Arial,sans-serif;font-size:12px;color:#888;">
                Geopolitical Digest
              </td>
            </tr>
          </table>

          <!-- Content -->
          {body_html}

          <!-- Footer -->
          <table width="100%" cellpadding="0" cellspacing="0"
                 style="border-top:1px solid #eee;margin-top:28px;padding-top:16px;">
            <tr>
              <td style="font-family:Arial,sans-serif;font-size:11px;
                         color:#aaa;text-align:center;">
                Sent via DocAnalyser &nbsp;·&nbsp;
                This digest was generated by AI and may contain errors.
              </td>
            </tr>
          </table>

        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _inline(text: str) -> str:
    """Apply inline markdown formatting within a line of text."""
    # Escape HTML special chars first
    text = text.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    # **bold**
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    # *italic* or _italic_
    text = re.sub(r'\*(.+?)\*',   r'<em>\1</em>', text)
    text = re.sub(r'_(.+?)_',     r'<em>\1</em>', text)
    return text


def markdown_to_plaintext(text: str) -> str:
    """Strip markdown markers to produce a plain-text fallback."""
    text = re.sub(r'^#{1,3}\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*',     r'\1', text)
    text = re.sub(r'_(.+?)_',       r'\1', text)
    return text


# ─────────────────────────────────────────────────────────────────────────────
# Contacts persistence
# ─────────────────────────────────────────────────────────────────────────────

def _contacts_path(data_dir: str) -> str:
    return os.path.join(data_dir, 'gmail_contacts.json')


def load_contacts(data_dir: str) -> List[dict]:
    """
    Load saved contacts.
    Returns list of dicts: [{'name': 'Alice Smith', 'email': 'alice@example.com'}, ...]
    """
    path = _contacts_path(data_dir)
    if not os.path.exists(path):
        return []
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except Exception as exc:
        logger.warning(f'load_contacts: {exc}')
        return []


def save_contacts(data_dir: str, contacts: List[dict]) -> bool:
    """Atomically save contacts list to disk."""
    path = _contacts_path(data_dir)
    try:
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as fh:
            json.dump(contacts, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
        return True
    except Exception as exc:
        logger.warning(f'save_contacts: {exc}')
        return False


def add_contact(data_dir: str, name: str, email: str) -> List[dict]:
    contacts = load_contacts(data_dir)
    email = email.strip().lower()
    if not any(c['email'].lower() == email for c in contacts):
        contacts.append({'name': name.strip(), 'email': email})
        save_contacts(data_dir, contacts)
    return contacts


def remove_contact(data_dir: str, email: str) -> List[dict]:
    contacts = [c for c in load_contacts(data_dir)
                if c['email'].lower() != email.strip().lower()]
    save_contacts(data_dir, contacts)
    return contacts


# ─────────────────────────────────────────────────────────────────────────────
# Gmail handler class
# ─────────────────────────────────────────────────────────────────────────────

class GmailHandler:
    """
    Manages Gmail OAuth authentication and message sending.

    Uses the same gdrive_credentials.json as the Drive integration
    but maintains a separate token file (gmail_token.json) so that
    Drive and Gmail authorisations are independent.
    """

    def __init__(self, data_dir: str):
        self.data_dir          = data_dir
        self.credentials_path  = os.path.join(data_dir, 'gdrive_credentials.json')
        self.token_path        = os.path.join(data_dir, 'gmail_token.json')
        self._creds            = None
        self._service          = None

    # ── Status ────────────────────────────────────────────────────────────────

    def is_available(self) -> bool:
        return GMAIL_AVAILABLE

    def has_credentials_file(self) -> bool:
        return os.path.exists(self.credentials_path)

    def is_authenticated(self) -> bool:
        return self._creds is not None and self._creds.valid

    def get_sender_email(self) -> Optional[str]:
        """Return the authenticated user's email address."""
        if not self._service:
            return None
        try:
            profile = self._service.users().getProfile(userId='me').execute()
            return profile.get('emailAddress')
        except Exception:
            return None

    # ── Authentication ────────────────────────────────────────────────────────

    def authenticate(self, force_new: bool = False) -> Tuple[bool, Optional[str]]:
        """
        Authenticate via OAuth 2.0.

        Opens a browser on first use; subsequent calls use the saved token.
        Returns (success, error_message_or_None).
        """
        if not GMAIL_AVAILABLE:
            return False, (
                "Google API packages are not installed.\n\n"
                "Run:  pip install google-api-python-client google-auth-oauthlib\n\n"
                "Then restart DocAnalyser."
            )

        if not self.has_credentials_file():
            return False, (
                f"Credentials file not found:\n{self.credentials_path}\n\n"
                "Download your OAuth credentials from Google Cloud Console\n"
                "(APIs & Services → Credentials → Download JSON)\n"
                f"and save as  gdrive_credentials.json  in:\n{self.data_dir}"
            )

        creds = None

        # Try loading saved token
        if not force_new and os.path.exists(self.token_path):
            try:
                creds = Credentials.from_authorized_user_file(
                    self.token_path, GMAIL_SCOPES
                )
            except Exception as exc:
                logger.warning(f'GmailHandler: could not load saved token: {exc}')
                creds = None

        # Refresh if expired
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as exc:
                logger.warning(f'GmailHandler: token refresh failed: {exc}')
                creds = None

        # Full OAuth flow if needed
        if not creds or not creds.valid:
            try:
                # SSL bypass for corporate/restrictive environments
                # (same pattern used in google_drive_handler.py)
                import ssl
                ssl._create_default_https_context = ssl._create_unverified_context

                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path, GMAIL_SCOPES
                )
                creds = flow.run_local_server(port=0, prompt='consent')
            except Exception as exc:
                return False, f"OAuth authorisation failed:\n{exc}"

        # Save token for next time
        try:
            with open(self.token_path, 'w') as fh:
                fh.write(creds.to_json())
        except Exception as exc:
            logger.warning(f'GmailHandler: could not save token: {exc}')

        self._creds = creds

        try:
            self._service = build('gmail', 'v1', credentials=creds)
        except Exception as exc:
            return False, f"Could not build Gmail service:\n{exc}"

        return True, None

    # ── Sending ───────────────────────────────────────────────────────────────

    def send_digest(
        self,
        subject:    str,
        html_body:  str,
        plain_body: str,
        recipients: List[str],
        sender_name: str = 'Ian Lucas',
    ) -> Tuple[bool, str]:
        """
        Send a digest email to one or more recipients.

        Args:
            subject:     Email subject line.
            html_body:   Full HTML email string.
            plain_body:  Plain-text fallback (shown by clients that don't render HTML).
            recipients:  List of email address strings.
            sender_name: Display name shown in the From field.

        Returns:
            (success, message)
        """
        if not self._service:
            ok, err = self.authenticate()
            if not ok:
                return False, err

        if not recipients:
            return False, "No recipients specified."

        errors  : List[str] = []
        sent    : int       = 0

        sender_email = self.get_sender_email() or 'me'

        for recipient in recipients:
            try:
                msg = MIMEMultipart('alternative')
                msg['Subject'] = subject
                msg['From']    = f'{sender_name} <{sender_email}>'
                msg['To']      = recipient

                # Plain text first, HTML second (RFC 2822: clients prefer last)
                msg.attach(MIMEText(plain_body, 'plain', 'utf-8'))
                msg.attach(MIMEText(html_body,  'html',  'utf-8'))

                raw = base64.urlsafe_b64encode(msg.as_bytes()).decode('utf-8')
                self._service.users().messages().send(
                    userId='me',
                    body={'raw': raw},
                ).execute()
                sent += 1
                logger.info(f'GmailHandler: sent to {recipient}')

            except Exception as exc:
                logger.warning(f'GmailHandler: failed to send to {recipient}: {exc}')
                errors.append(f'{recipient}: {exc}')

        if errors:
            error_detail = '\n'.join(errors)
            if sent > 0:
                return True, (
                    f"Sent to {sent} recipient(s).\n\n"
                    f"Failed ({len(errors)}):\n{error_detail}"
                )
            return False, f"All sends failed:\n{error_detail}"

        return True, f"Sent to {sent} recipient(s)."


# ─────────────────────────────────────────────────────────────────────────────
# Module-level convenience singleton
# ─────────────────────────────────────────────────────────────────────────────

_handler: Optional[GmailHandler] = None


def get_gmail_handler(data_dir: str) -> GmailHandler:
    """Return (creating if needed) the module-level GmailHandler instance."""
    global _handler
    if _handler is None or _handler.data_dir != data_dir:
        _handler = GmailHandler(data_dir)
    return _handler
