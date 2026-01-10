from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
from app.database import get_db
from app.models import User, GmailAccount, Category, Email
from app.schemas import (
    EmailResponse,
    EmailDetailResponse,
    BulkEmailAction,
    UnsubscribeResult,
    SyncResponse,
    CategoryBreakdown,
)
from app.routers.auth import get_current_user
from app.services.gmail import GmailService
from app.services.ai import AIService
from app.services.unsubscribe import async_unsubscribe
from app.utils import decrypt_token
import asyncio
from concurrent.futures import ThreadPoolExecutor

router = APIRouter(prefix="/api/emails", tags=["emails"])

executor = ThreadPoolExecutor(max_workers=4)


def email_to_response(email: Email, account_email: str = None) -> dict:
    """Convert Email model to response dict with account_email."""
    return {
        "id": email.id,
        "gmail_account_id": email.gmail_account_id,
        "account_email": account_email,
        "category_id": email.category_id,
        "gmail_message_id": email.gmail_message_id,
        "subject": email.subject,
        "sender": email.sender,
        "sender_email": email.sender_email,
        "received_at": email.received_at,
        "ai_summary": email.ai_summary,
        "is_read": email.is_read,
        "created_at": email.created_at,
        "body_text": getattr(email, 'body_text', None),
        "body_html": getattr(email, 'body_html', None),
        "thread_id": getattr(email, 'thread_id', None),
    }


@router.get("", response_model=list[EmailResponse])
async def list_emails(
    category_id: Optional[int] = None,
    account_id: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List emails, optionally filtered by category or account."""
    query = (
        db.query(Email, GmailAccount.email)
        .join(GmailAccount)
        .filter(GmailAccount.user_id == current_user.id)
    )

    if category_id is not None:
        query = query.filter(Email.category_id == category_id)

    if account_id is not None:
        query = query.filter(Email.gmail_account_id == account_id)

    results = (
        query.order_by(Email.received_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return [email_to_response(email, account_email) for email, account_email in results]


@router.get("/uncategorized", response_model=list[EmailResponse])
async def list_uncategorized_emails(
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List emails that haven't been categorized."""
    results = (
        db.query(Email, GmailAccount.email)
        .join(GmailAccount)
        .filter(
            GmailAccount.user_id == current_user.id,
            Email.category_id.is_(None)
        )
        .order_by(Email.received_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    return [email_to_response(email, account_email) for email, account_email in results]


@router.get("/{email_id}", response_model=EmailDetailResponse)
async def get_email(
    email_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get full email details including body."""
    result = (
        db.query(Email, GmailAccount.email)
        .join(GmailAccount)
        .filter(Email.id == email_id, GmailAccount.user_id == current_user.id)
        .first()
    )

    if not result:
        raise HTTPException(status_code=404, detail="Email not found")

    email, account_email = result

    if not email.is_read:
        email.is_read = True
        db.commit()

    return email_to_response(email, account_email)


@router.post("/sync", response_model=SyncResponse)
async def sync_emails(
    account_id: Optional[int] = None,
    max_results: int = 50,
    older_than_date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Sync emails from Gmail, categorize them with AI, and archive.
    - For new emails: only fetches emails newer than the most recent synced email
    - For historical import: use older_than_date parameter (format: YYYY-MM-DD)
    """
    if account_id:
        accounts = [
            db.query(GmailAccount)
            .filter(
                GmailAccount.id == account_id,
                GmailAccount.user_id == current_user.id
            )
            .first()
        ]
        if not accounts[0]:
            raise HTTPException(status_code=404, detail="Account not found")
    else:
        accounts = (
            db.query(GmailAccount)
            .filter(GmailAccount.user_id == current_user.id)
            .all()
        )

    if not accounts:
        raise HTTPException(status_code=400, detail="No Gmail accounts connected")

    categories = (
        db.query(Category)
        .filter(Category.user_id == current_user.id)
        .all()
    )

    category_data = [
        {"id": cat.id, "name": cat.name, "description": cat.description}
        for cat in categories
    ]

    ai_service = AIService()
    synced_count = 0
    categorized_count = 0
    uncategorized_count = 0
    archived_count = 0
    category_counts = {}  # {category_id: count}

    # Build category name lookup
    category_names = {cat.id: cat.name for cat in categories}
    category_names[None] = "Uncategorized"
    last_synced = None

    for account in accounts:
        access_token = decrypt_token(account.access_token)
        refresh_token = decrypt_token(account.refresh_token) if account.refresh_token else None

        try:
            gmail = GmailService(access_token, refresh_token)

            # Build query based on sync type
            if older_than_date:
                # Historical import: get emails before the specified date
                # Convert YYYY-MM-DD to YYYY/MM/DD for Gmail
                formatted_date = older_than_date.replace("-", "/")
                # Search all mail, not just inbox (older emails may be archived)
                query = f"before:{formatted_date}"
                print(f"=== HISTORICAL IMPORT ===")
                print(f"Date received: {older_than_date}")
                print(f"Formatted date: {formatted_date}")
                print(f"Query: {query}")
                print(f"Max results: {max_results}")
            else:
                # New emails: get emails after the most recent synced email
                most_recent = (
                    db.query(Email)
                    .filter(Email.gmail_account_id == account.id)
                    .order_by(Email.received_at.desc())
                    .first()
                )
                if most_recent and most_recent.received_at:
                    # Format date for Gmail query (YYYY/MM/DD)
                    after_date = most_recent.received_at.strftime("%Y/%m/%d")
                    query = f"in:inbox after:{after_date}"
                else:
                    # First sync - get recent emails from inbox
                    query = "in:inbox"
                print(f"New emails query: {query}")

            messages = gmail.get_messages(max_results=max_results, query=query)
            print(f"Messages returned from Gmail: {len(messages)}")

            # Collect all new emails first
            emails_to_process = []
            email_details_map = {}
            skipped_existing = 0

            for msg in messages:
                existing = (
                    db.query(Email)
                    .filter(
                        Email.gmail_account_id == account.id,
                        Email.gmail_message_id == msg["id"]
                    )
                    .first()
                )

                if existing:
                    skipped_existing += 1
                    continue

                try:
                    details = gmail.get_message_detail(msg["id"])
                    temp_id = msg["id"]
                    emails_to_process.append({
                        "id": temp_id,
                        "subject": details.get("subject", ""),
                        "sender": details.get("sender", ""),
                        "body_text": details.get("body_text", ""),
                    })
                    email_details_map[temp_id] = details
                except Exception as e:
                    print(f"Failed to get message details: {e}")
                    continue

            print(f"Skipped (already imported): {skipped_existing}")
            print(f"New emails to process: {len(emails_to_process)}")

            # Process all emails in one AI call
            if emails_to_process:
                ai_results = ai_service.process_emails_batch(emails_to_process, category_data)
                results_map = {r["id"]: r for r in ai_results}

                # Create email records
                for temp_id, details in email_details_map.items():
                    ai_result = results_map.get(temp_id, {})
                    category_id = ai_result.get("category_id")
                    summary = ai_result.get("summary", f"Email from {details.get('sender', 'unknown')}")

                    # Track category counts
                    category_counts[category_id] = category_counts.get(category_id, 0) + 1
                    if category_id:
                        categorized_count += 1
                    else:
                        uncategorized_count += 1

                    email_record = Email(
                        gmail_account_id=account.id,
                        category_id=category_id,
                        gmail_message_id=details["gmail_message_id"],
                        thread_id=details.get("thread_id"),
                        subject=details.get("subject"),
                        sender=details.get("sender"),
                        sender_email=details.get("sender_email"),
                        received_at=details.get("received_at"),
                        body_text=details.get("body_text"),
                        body_html=details.get("body_html"),
                        ai_summary=summary,
                    )
                    db.add(email_record)
                    synced_count += 1

                    try:
                        gmail.archive_message(temp_id)
                        archived_count += 1
                    except Exception as e:
                        print(f"Failed to archive message: {e}")

                db.commit()

            # Update last_synced_at for this account
            account.last_synced_at = datetime.utcnow()
            last_synced = account.last_synced_at
            db.commit()

        except Exception as e:
            print(f"Error syncing account {account.email}: {e}")
            continue

    # Build category breakdown
    category_breakdown = [
        CategoryBreakdown(
            category_id=cat_id,
            category_name=category_names.get(cat_id, "Unknown"),
            count=count
        )
        for cat_id, count in category_counts.items()
    ]
    # Sort by count descending, with Uncategorized last
    category_breakdown.sort(key=lambda x: (x.category_id is None, -x.count))

    return SyncResponse(
        synced_count=synced_count,
        categorized_count=categorized_count,
        uncategorized_count=uncategorized_count,
        archived_count=archived_count,
        category_breakdown=category_breakdown,
        last_synced_at=last_synced,
    )


@router.post("/recategorize", response_model=SyncResponse)
async def recategorize_emails(
    only_uncategorized: bool = True,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Re-run AI categorization on existing emails.
    - only_uncategorized=True: Only recategorize emails without a category
    - only_uncategorized=False: Recategorize ALL emails
    """
    # Get user's categories
    categories = (
        db.query(Category)
        .filter(Category.user_id == current_user.id)
        .all()
    )

    if not categories:
        raise HTTPException(status_code=400, detail="No categories defined. Create categories first.")

    category_data = [
        {"id": cat.id, "name": cat.name, "description": cat.description}
        for cat in categories
    ]

    # Build category name lookup
    category_names = {cat.id: cat.name for cat in categories}
    category_names[None] = "Uncategorized"

    # Get emails to recategorize
    query = (
        db.query(Email)
        .join(GmailAccount)
        .filter(GmailAccount.user_id == current_user.id)
    )

    if only_uncategorized:
        query = query.filter(Email.category_id.is_(None))

    emails = query.all()

    if not emails:
        return SyncResponse(
            synced_count=0,
            categorized_count=0,
            uncategorized_count=0,
            archived_count=0,
            category_breakdown=[],
        )

    # Prepare emails for batch processing
    emails_to_process = [
        {
            "id": email.id,
            "subject": email.subject or "",
            "sender": email.sender or "",
            "body_text": email.body_text or "",
        }
        for email in emails
    ]

    # Process with AI
    ai_service = AIService()
    ai_results = ai_service.process_emails_batch(emails_to_process, category_data)
    results_map = {r["id"]: r for r in ai_results}

    # Update emails
    categorized_count = 0
    uncategorized_count = 0
    category_counts = {}

    for email in emails:
        ai_result = results_map.get(email.id, {})
        new_category_id = ai_result.get("category_id")
        new_summary = ai_result.get("summary")

        # Update category
        email.category_id = new_category_id
        if new_summary:
            email.ai_summary = new_summary

        # Track counts
        category_counts[new_category_id] = category_counts.get(new_category_id, 0) + 1
        if new_category_id:
            categorized_count += 1
        else:
            uncategorized_count += 1

    db.commit()

    # Build category breakdown
    category_breakdown = [
        CategoryBreakdown(
            category_id=cat_id,
            category_name=category_names.get(cat_id, "Unknown"),
            count=count
        )
        for cat_id, count in category_counts.items()
    ]
    category_breakdown.sort(key=lambda x: (x.category_id is None, -x.count))

    return SyncResponse(
        synced_count=len(emails),
        categorized_count=categorized_count,
        uncategorized_count=uncategorized_count,
        archived_count=0,
        category_breakdown=category_breakdown,
    )


@router.post("/delete")
async def bulk_delete_emails(
    action: BulkEmailAction,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete multiple emails (moves to trash in Gmail)."""
    emails = (
        db.query(Email)
        .join(GmailAccount)
        .filter(
            Email.id.in_(action.email_ids),
            GmailAccount.user_id == current_user.id
        )
        .all()
    )

    if not emails:
        raise HTTPException(status_code=404, detail="No emails found")

    deleted_count = 0
    errors = []

    accounts_cache = {}

    for email in emails:
        if email.gmail_account_id not in accounts_cache:
            account = db.query(GmailAccount).filter(
                GmailAccount.id == email.gmail_account_id
            ).first()
            if account:
                access_token = decrypt_token(account.access_token)
                refresh_token = decrypt_token(account.refresh_token) if account.refresh_token else None
                accounts_cache[email.gmail_account_id] = GmailService(
                    access_token, refresh_token
                )

        gmail = accounts_cache.get(email.gmail_account_id)
        if not gmail:
            errors.append(f"No Gmail service for email {email.id}")
            continue

        try:
            gmail.delete_message(email.gmail_message_id)
            db.delete(email)
            deleted_count += 1
        except Exception as e:
            errors.append(f"Failed to delete email {email.id}: {str(e)}")

    db.commit()

    return {
        "deleted_count": deleted_count,
        "errors": errors if errors else None,
    }


@router.post("/unsubscribe", response_model=list[UnsubscribeResult])
async def bulk_unsubscribe(
    action: BulkEmailAction,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Attempt to unsubscribe from multiple email senders using AI agent."""
    emails = (
        db.query(Email)
        .join(GmailAccount)
        .filter(
            Email.id.in_(action.email_ids),
            GmailAccount.user_id == current_user.id
        )
        .all()
    )

    if not emails:
        raise HTTPException(status_code=404, detail="No emails found")

    results = []

    for email in emails:
        body_html = email.body_html or ""
        body_text = email.body_text or ""

        gmail_service = GmailService.__new__(GmailService)
        unsubscribe_link = gmail_service.find_unsubscribe_link(body_html, body_text)

        if not unsubscribe_link:
            results.append(UnsubscribeResult(
                email_id=email.id,
                success=False,
                message="No unsubscribe link found in email"
            ))
            continue

        try:
            result = await async_unsubscribe(unsubscribe_link, email.sender_email)

            results.append(UnsubscribeResult(
                email_id=email.id,
                success=result.get("success", False),
                message=result.get("message", "Unknown result")
            ))
        except Exception as e:
            results.append(UnsubscribeResult(
                email_id=email.id,
                success=False,
                message=f"Error: {str(e)}"
            ))

    return results


@router.put("/{email_id}/category")
async def update_email_category(
    email_id: int,
    category_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update the category of an email."""
    email = (
        db.query(Email)
        .join(GmailAccount)
        .filter(Email.id == email_id, GmailAccount.user_id == current_user.id)
        .first()
    )

    if not email:
        raise HTTPException(status_code=404, detail="Email not found")

    if category_id is not None:
        category = (
            db.query(Category)
            .filter(Category.id == category_id, Category.user_id == current_user.id)
            .first()
        )
        if not category:
            raise HTTPException(status_code=404, detail="Category not found")

    email.category_id = category_id
    db.commit()

    return {"message": "Email category updated"}
