from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from datetime import datetime
from typing import Optional
import base64
import email
from email.utils import parsedate_to_datetime
from bs4 import BeautifulSoup
import re
from app.config import get_settings


class GmailService:
    SCOPES = [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.modify",
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
    ]

    def __init__(self, access_token: str, refresh_token: Optional[str] = None):
        settings = get_settings()
        self.credentials = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
        )
        self.service = build("gmail", "v1", credentials=self.credentials)

    def get_messages(self, max_results: int = 50, query: str = "is:unread") -> list[dict]:
        """Fetch messages from Gmail inbox."""
        try:
            results = self.service.users().messages().list(
                userId="me",
                maxResults=max_results,
                q=query
            ).execute()

            messages = results.get("messages", [])
            return messages
        except HttpError as e:
            raise Exception(f"Failed to fetch messages: {e}")

    def get_message_detail(self, message_id: str) -> dict:
        """Fetch full message details including body."""
        try:
            message = self.service.users().messages().get(
                userId="me",
                id=message_id,
                format="full"
            ).execute()

            return self._parse_message(message)
        except HttpError as e:
            raise Exception(f"Failed to fetch message {message_id}: {e}")

    def _parse_message(self, message: dict) -> dict:
        """Parse Gmail message into a structured format."""
        headers = {h["name"].lower(): h["value"] for h in message["payload"].get("headers", [])}

        subject = headers.get("subject", "(No Subject)")
        sender = headers.get("from", "")
        date_str = headers.get("date", "")

        sender_name, sender_email = self._parse_sender(sender)
        received_at = self._parse_date(date_str)

        body_text, body_html = self._extract_body(message["payload"])

        return {
            "gmail_message_id": message["id"],
            "thread_id": message.get("threadId"),
            "subject": subject,
            "sender": sender_name or sender_email,
            "sender_email": sender_email,
            "received_at": received_at,
            "body_text": body_text,
            "body_html": body_html,
        }

    def _parse_sender(self, sender: str) -> tuple[str, str]:
        """Extract name and email from sender string."""
        match = re.match(r"(.+?)\s*<(.+?)>", sender)
        if match:
            return match.group(1).strip().strip('"'), match.group(2).strip()
        return "", sender.strip()

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse email date string to datetime."""
        if not date_str:
            return None
        try:
            return parsedate_to_datetime(date_str)
        except (ValueError, TypeError):
            return None

    def _extract_body(self, payload: dict) -> tuple[str, str]:
        """Extract text and HTML body from message payload."""
        body_text = ""
        body_html = ""

        if "parts" in payload:
            for part in payload["parts"]:
                mime_type = part.get("mimeType", "")
                if mime_type == "text/plain" and not body_text:
                    body_text = self._decode_body(part.get("body", {}).get("data", ""))
                elif mime_type == "text/html" and not body_html:
                    body_html = self._decode_body(part.get("body", {}).get("data", ""))
                elif "parts" in part:
                    nested_text, nested_html = self._extract_body(part)
                    body_text = body_text or nested_text
                    body_html = body_html or nested_html
        else:
            data = payload.get("body", {}).get("data", "")
            mime_type = payload.get("mimeType", "")
            if mime_type == "text/plain":
                body_text = self._decode_body(data)
            elif mime_type == "text/html":
                body_html = self._decode_body(data)

        if not body_text and body_html:
            soup = BeautifulSoup(body_html, "html.parser")
            body_text = soup.get_text(separator="\n", strip=True)

        return body_text, body_html

    def _decode_body(self, data: str) -> str:
        """Decode base64url encoded body."""
        if not data:
            return ""
        try:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
        except Exception:
            return ""

    def archive_message(self, message_id: str) -> bool:
        """Archive a message by removing INBOX label."""
        try:
            self.service.users().messages().modify(
                userId="me",
                id=message_id,
                body={"removeLabelIds": ["INBOX"]}
            ).execute()
            return True
        except HttpError as e:
            raise Exception(f"Failed to archive message {message_id}: {e}")

    def delete_message(self, message_id: str) -> bool:
        """Move message to trash."""
        try:
            self.service.users().messages().trash(
                userId="me",
                id=message_id
            ).execute()
            return True
        except HttpError as e:
            raise Exception(f"Failed to delete message {message_id}: {e}")

    def find_unsubscribe_link(self, body_html: str, body_text: str) -> Optional[str]:
        """Find unsubscribe link in email body."""
        patterns = [
            r'href=["\']([^"\']*unsubscribe[^"\']*)["\']',
            r'href=["\']([^"\']*opt.?out[^"\']*)["\']',
            r'href=["\']([^"\']*remove[^"\']*)["\']',
        ]

        content = body_html or body_text

        for pattern in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                return matches[0]

        soup = BeautifulSoup(body_html, "html.parser") if body_html else None
        if soup:
            for link in soup.find_all("a"):
                text = link.get_text().lower()
                if "unsubscribe" in text or "opt out" in text or "opt-out" in text:
                    href = link.get("href")
                    if href:
                        return href

        return None

    def watch(self, topic_name: str) -> dict:
        """
        Set up push notifications for the mailbox.

        Args:
            topic_name: Full Pub/Sub topic name (projects/{project}/topics/{topic})

        Returns:
            dict with historyId and expiration
        """
        try:
            request_body = {
                "topicName": topic_name,
                "labelIds": ["INBOX"],
                "labelFilterBehavior": "INCLUDE",
            }
            response = self.service.users().watch(
                userId="me",
                body=request_body
            ).execute()

            return {
                "history_id": response.get("historyId"),
                "expiration": response.get("expiration"),  # Unix timestamp in ms
            }
        except HttpError as e:
            raise Exception(f"Failed to set up watch: {e}")

    def stop_watch(self) -> bool:
        """Stop push notifications for the mailbox."""
        try:
            self.service.users().stop(userId="me").execute()
            return True
        except HttpError as e:
            raise Exception(f"Failed to stop watch: {e}")

    def get_history(self, start_history_id: str) -> list[dict]:
        """
        Get mailbox changes since the given history ID.

        Returns list of message IDs that were added to INBOX.
        """
        try:
            results = self.service.users().history().list(
                userId="me",
                startHistoryId=start_history_id,
                historyTypes=["messageAdded"],
                labelId="INBOX"
            ).execute()

            message_ids = []
            for history in results.get("history", []):
                for msg_added in history.get("messagesAdded", []):
                    message = msg_added.get("message", {})
                    if "INBOX" in message.get("labelIds", []):
                        message_ids.append(message["id"])

            return message_ids
        except HttpError as e:
            # History ID might be too old
            if "404" in str(e) or "historyId" in str(e).lower():
                return []
            raise Exception(f"Failed to get history: {e}")

    def get_profile(self) -> dict:
        """Get the user's Gmail profile including current historyId."""
        try:
            profile = self.service.users().getProfile(userId="me").execute()
            return {
                "email": profile.get("emailAddress"),
                "history_id": profile.get("historyId"),
            }
        except HttpError as e:
            raise Exception(f"Failed to get profile: {e}")
