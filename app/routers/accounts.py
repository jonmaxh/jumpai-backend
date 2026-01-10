from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from app.database import get_db
from app.config import get_settings
from app.models import User, GmailAccount
from app.schemas import GmailAccountResponse
from app.routers.auth import get_current_user
from app.services.gmail import GmailService
from app.utils import decrypt_token

settings = get_settings()

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("", response_model=list[GmailAccountResponse])
async def list_accounts(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all connected Gmail accounts for the current user."""
    accounts = (
        db.query(GmailAccount)
        .filter(GmailAccount.user_id == current_user.id)
        .order_by(GmailAccount.created_at.desc())
        .all()
    )
    return accounts


@router.delete("/{account_id}")
async def disconnect_account(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Disconnect a Gmail account."""
    account = (
        db.query(GmailAccount)
        .filter(GmailAccount.id == account_id, GmailAccount.user_id == current_user.id)
        .first()
    )

    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    if account.email == current_user.email:
        other_accounts = (
            db.query(GmailAccount)
            .filter(
                GmailAccount.user_id == current_user.id,
                GmailAccount.id != account_id
            )
            .count()
        )
        if other_accounts == 0:
            raise HTTPException(
                status_code=400,
                detail="Cannot disconnect your primary account without other accounts connected"
            )

    db.delete(account)
    db.commit()

    return {"message": "Account disconnected successfully"}


@router.post("/{account_id}/watch")
async def enable_watch(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Enable Gmail push notifications for an account.

    This sets up a watch on the Gmail mailbox to receive push notifications
    when new emails arrive. Requires Pub/Sub to be configured.
    """
    if not settings.push_notifications_enabled:
        raise HTTPException(
            status_code=400,
            detail="Push notifications not configured. Set PUBSUB_TOPIC in environment."
        )

    account = (
        db.query(GmailAccount)
        .filter(GmailAccount.id == account_id, GmailAccount.user_id == current_user.id)
        .first()
    )

    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    try:
        access_token = decrypt_token(account.access_token)
        refresh_token = decrypt_token(account.refresh_token) if account.refresh_token else None
        gmail = GmailService(access_token, refresh_token)

        # Set up the watch
        result = gmail.watch(settings.pubsub_topic)

        # Store the history ID and expiration
        account.last_history_id = result["history_id"]
        if result["expiration"]:
            # Convert ms timestamp to datetime
            account.watch_expiration = datetime.fromtimestamp(int(result["expiration"]) / 1000)

        db.commit()

        return {
            "message": "Push notifications enabled",
            "history_id": result["history_id"],
            "expiration": account.watch_expiration.isoformat() if account.watch_expiration else None,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to enable watch: {str(e)}")


@router.delete("/{account_id}/watch")
async def disable_watch(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Disable Gmail push notifications for an account.
    """
    account = (
        db.query(GmailAccount)
        .filter(GmailAccount.id == account_id, GmailAccount.user_id == current_user.id)
        .first()
    )

    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    try:
        access_token = decrypt_token(account.access_token)
        refresh_token = decrypt_token(account.refresh_token) if account.refresh_token else None
        gmail = GmailService(access_token, refresh_token)

        # Stop the watch
        gmail.stop_watch()

        # Clear the watch expiration
        account.watch_expiration = None
        db.commit()

        return {"message": "Push notifications disabled"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to disable watch: {str(e)}")


@router.get("/{account_id}/watch")
async def get_watch_status(
    account_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get the watch status for an account.
    """
    account = (
        db.query(GmailAccount)
        .filter(GmailAccount.id == account_id, GmailAccount.user_id == current_user.id)
        .first()
    )

    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    is_active = False
    if account.watch_expiration:
        is_active = account.watch_expiration > datetime.utcnow()

    return {
        "push_notifications_configured": settings.push_notifications_enabled,
        "watch_active": is_active,
        "watch_expiration": account.watch_expiration.isoformat() if account.watch_expiration else None,
        "last_history_id": account.last_history_id,
    }
