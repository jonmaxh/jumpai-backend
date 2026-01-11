from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.models import Email, GmailAccount, Category
from app.routers.webhooks import process_gmail_notification
from app.utils import encrypt_token


@pytest.mark.asyncio
async def test_process_gmail_notification_categorizes_and_archives(db, test_user):
    account = GmailAccount(
        user_id=test_user.id,
        email="test@example.com",
        access_token=encrypt_token("access-token"),
        refresh_token=encrypt_token("refresh-token"),
        last_history_id="123",
    )
    category = Category(
        user_id=test_user.id,
        name="Invoices",
        description="Billing and receipts",
    )
    db.add(account)
    db.add(category)
    db.commit()
    db.refresh(account)
    db.refresh(category)

    gmail_mock = MagicMock()
    gmail_mock.get_history.return_value = ["msg_1"]
    gmail_mock.get_message_detail.return_value = {
        "gmail_message_id": "msg_1",
        "thread_id": "thread_1",
        "subject": "Invoice",
        "sender": "Vendor",
        "sender_email": "vendor@example.com",
        "received_at": datetime.utcnow(),
        "body_text": "Here is your invoice.",
        "body_html": "<p>Here is your invoice.</p>",
    }

    ai_mock = MagicMock()
    ai_mock.process_email.return_value = (category.id, "Invoice summary")

    with patch("app.routers.webhooks.GmailService", return_value=gmail_mock), \
        patch("app.routers.webhooks.AIService", return_value=ai_mock), \
        patch("app.routers.webhooks.publish") as publish_mock:
        await process_gmail_notification(account.id, "456", db)

    email = db.query(Email).filter(Email.gmail_account_id == account.id).first()
    assert email is not None
    assert email.category_id == category.id
    assert email.ai_summary == "Invoice summary"

    gmail_mock.archive_message.assert_called_once_with("msg_1")

    publish_mock.assert_called_once()
    args, _ = publish_mock.call_args
    assert args[0] == account.user_id
    assert args[1]["event"] == "emails_synced"
    assert args[1]["synced_count"] == 1

    db.refresh(account)
    assert account.last_history_id == "456"
    assert account.last_synced_at is not None
