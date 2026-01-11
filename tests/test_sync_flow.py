from datetime import datetime
from unittest.mock import MagicMock, patch

from app.models import Email


def test_sync_archives_all_emails(authenticated_client, test_gmail_account, test_category, db):
    gmail_mock = MagicMock()
    gmail_mock.get_messages.return_value = [{"id": "msg_1"}, {"id": "msg_2"}]
    gmail_mock.get_message_detail.side_effect = [
        {
            "gmail_message_id": "msg_1",
            "thread_id": "thread_1",
            "subject": "Invoice 1",
            "sender": "Vendor",
            "sender_email": "vendor@example.com",
            "received_at": datetime.utcnow(),
            "body_text": "Invoice body 1",
            "body_html": "<p>Invoice body 1</p>",
        },
        {
            "gmail_message_id": "msg_2",
            "thread_id": "thread_2",
            "subject": "Newsletter",
            "sender": "News",
            "sender_email": "news@example.com",
            "received_at": datetime.utcnow(),
            "body_text": "Newsletter body",
            "body_html": "<p>Newsletter body</p>",
        },
    ]

    ai_mock = MagicMock()
    ai_mock.process_emails_batch.return_value = [
        {"id": "msg_1", "category_id": test_category.id, "summary": "Invoice summary"},
        {"id": "msg_2", "category_id": None, "summary": "Newsletter summary"},
    ]

    with patch("app.routers.emails.GmailService", return_value=gmail_mock), \
        patch("app.routers.emails.AIService", return_value=ai_mock):
        response = authenticated_client.post("/api/emails/sync")

    assert response.status_code == 200
    assert response.json()["synced_count"] == 2

    gmail_mock.archive_message.assert_any_call("msg_1")
    gmail_mock.archive_message.assert_any_call("msg_2")
    assert gmail_mock.archive_message.call_count == 2

    emails = (
        db.query(Email)
        .filter(Email.gmail_account_id == test_gmail_account.id)
        .all()
    )
    assert len(emails) == 2
    assert any(email.category_id is None for email in emails)
