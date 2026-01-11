from fastapi import APIRouter, Request, HTTPException, Depends, BackgroundTasks
from sqlalchemy.orm import Session
import base64
import json
from datetime import datetime
from app.database import get_db
from app.config import get_settings
from app.models import GmailAccount, Email, Category
from app.services.gmail import GmailService
from app.services.ai import AIService
from app.utils import decrypt_token

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])
settings = get_settings()


async def process_gmail_notification(
    account_id: int,
    history_id: str,
    db: Session,
):
    """Process incoming Gmail notification and sync new emails."""
    account = db.query(GmailAccount).filter(GmailAccount.id == account_id).first()
    if not account:
        return

    try:
        access_token = decrypt_token(account.access_token)
        refresh_token = decrypt_token(account.refresh_token) if account.refresh_token else None
        gmail = GmailService(access_token, refresh_token)

        # Get new message IDs since last history ID
        if account.last_history_id:
            new_message_ids = gmail.get_history(account.last_history_id)
        else:
            # No history ID, skip incremental sync
            new_message_ids = []

        if not new_message_ids:
            # Update history ID even if no new messages
            account.last_history_id = history_id
            db.commit()
            return

        # Get user's categories for AI categorization
        categories = db.query(Category).filter(Category.user_id == account.user_id).all()
        category_data = [
            {"id": cat.id, "name": cat.name, "description": cat.description}
            for cat in categories
        ]
        ai_service = AIService()

        synced_count = 0
        archived_count = 0
        for msg_id in new_message_ids:
            # Check if already exists
            existing = db.query(Email).filter(
                Email.gmail_account_id == account.id,
                Email.gmail_message_id == msg_id
            ).first()

            if existing:
                continue

            try:
                msg_detail = gmail.get_message_detail(msg_id)

                # AI categorization + summary
                category_id, ai_summary = ai_service.process_email(
                    subject=msg_detail["subject"],
                    sender=msg_detail["sender"],
                    body_text=msg_detail.get("body_text") or "",
                    categories=category_data,
                )

                email = Email(
                    gmail_account_id=account.id,
                    gmail_message_id=msg_detail["gmail_message_id"],
                    thread_id=msg_detail.get("thread_id"),
                    subject=msg_detail["subject"],
                    sender=msg_detail["sender"],
                    sender_email=msg_detail.get("sender_email"),
                    received_at=msg_detail["received_at"],
                    body_text=msg_detail["body_text"],
                    body_html=msg_detail["body_html"],
                    category_id=category_id,
                    ai_summary=ai_summary,
                )
                db.add(email)
                synced_count += 1
                try:
                    gmail.archive_message(msg_id)
                    archived_count += 1
                except Exception as e:
                    print(f"Failed to archive message {msg_id}: {e}")

            except Exception as e:
                print(f"Error processing message {msg_id}: {e}")
                continue

        # Update account's history ID and last synced time
        account.last_history_id = history_id
        account.last_synced_at = datetime.utcnow()
        db.commit()

        print(
            f"Push notification processed: synced {synced_count} new emails "
            f"(archived {archived_count}) for account {account.email}"
        )

    except Exception as e:
        print(f"Error processing Gmail notification for account {account_id}: {e}")


@router.post("/gmail")
async def gmail_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """
    Webhook endpoint for Gmail push notifications via Pub/Sub.

    Google Pub/Sub sends POST requests with the following format:
    {
        "message": {
            "data": "<base64-encoded-data>",
            "messageId": "...",
            "publishTime": "..."
        },
        "subscription": "projects/.../subscriptions/..."
    }

    The decoded data contains:
    {
        "emailAddress": "user@gmail.com",
        "historyId": "12345"
    }
    """
    # Verify the request if verification token is configured
    if settings.pubsub_verification_token:
        token = request.query_params.get("token")
        if token != settings.pubsub_verification_token:
            raise HTTPException(status_code=403, detail="Invalid verification token")

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    message = body.get("message", {})
    data_b64 = message.get("data")

    if not data_b64:
        # Could be a verification request from Google
        return {"status": "ok"}

    try:
        data_json = base64.urlsafe_b64decode(data_b64).decode("utf-8")
        data = json.loads(data_json)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid message data")

    email_address = data.get("emailAddress")
    history_id = data.get("historyId")

    if not email_address or not history_id:
        raise HTTPException(status_code=400, detail="Missing emailAddress or historyId")

    # Find the Gmail account for this email
    account = db.query(GmailAccount).filter(GmailAccount.email == email_address).first()

    if not account:
        # Unknown account, ignore
        return {"status": "ignored", "reason": "unknown account"}

    # Check if user has auto_sync enabled
    from app.models import User
    user = db.query(User).filter(User.id == account.user_id).first()
    if not user or not user.auto_sync_enabled:
        return {"status": "ignored", "reason": "auto sync disabled"}

    # Process the notification in the background
    background_tasks.add_task(
        process_gmail_notification,
        account_id=account.id,
        history_id=history_id,
        db=db,
    )

    return {"status": "processing"}
