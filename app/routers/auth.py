from fastapi import APIRouter, Depends, HTTPException, Response, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from google_auth_oauthlib.flow import Flow
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
import httpx
from datetime import datetime, timedelta
from jose import jwt
from app.database import get_db
from app.config import get_settings
from app.models import User, GmailAccount
from app.schemas import UserResponse
from app.utils import encrypt_token, decrypt_token
from app.services.gmail import GmailService

router = APIRouter(prefix="/api/auth", tags=["auth"])
settings = get_settings()

JWT_ALGORITHM = "HS256"
JWT_EXPIRY_DAYS = 7


def create_jwt_token(user_id: int) -> str:
    expiry = datetime.utcnow() + timedelta(days=JWT_EXPIRY_DAYS)
    payload = {"sub": str(user_id), "exp": expiry}
    return jwt.encode(payload, settings.secret_key, algorithm=JWT_ALGORITHM)


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get("session_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[JWT_ALGORITHM])
        user_id = int(payload["sub"])
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user


def get_optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    try:
        return get_current_user(request, db)
    except HTTPException:
        return None


@router.get("/google")
async def google_auth(request: Request):
    """Initiate Google OAuth flow."""
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=GmailService.SCOPES,
        redirect_uri=settings.google_redirect_uri,
    )

    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )

    response = RedirectResponse(url=auth_url)
    response.set_cookie(
        key="oauth_state",
        value=state,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=600,
    )

    return response


@router.get("/google/callback")
async def google_callback(
    request: Request,
    code: str,
    state: str,
    db: Session = Depends(get_db),
):
    """Handle Google OAuth callback."""
    stored_state = request.cookies.get("oauth_state")
    if not stored_state or stored_state != state:
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=GmailService.SCOPES,
        redirect_uri=settings.google_redirect_uri,
        state=state,
    )

    flow.fetch_token(code=code)
    credentials = flow.credentials

    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {credentials.token}"},
        )
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to get user info")
        user_info = response.json()

    email = user_info.get("email")
    name = user_info.get("name")
    picture = user_info.get("picture")

    if not email:
        raise HTTPException(status_code=400, detail="Email not provided")

    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(email=email, name=name, picture=picture)
        db.add(user)
        db.commit()
        db.refresh(user)

    gmail_account = (
        db.query(GmailAccount)
        .filter(GmailAccount.user_id == user.id, GmailAccount.email == email)
        .first()
    )

    encrypted_access = encrypt_token(credentials.token)
    encrypted_refresh = encrypt_token(credentials.refresh_token) if credentials.refresh_token else None

    if gmail_account:
        gmail_account.access_token = encrypted_access
        gmail_account.refresh_token = encrypted_refresh or gmail_account.refresh_token
        gmail_account.token_expiry = credentials.expiry
    else:
        gmail_account = GmailAccount(
            user_id=user.id,
            email=email,
            access_token=encrypted_access,
            refresh_token=encrypted_refresh,
            token_expiry=credentials.expiry,
        )
        db.add(gmail_account)

    db.commit()

    token = create_jwt_token(user.id)

    response = RedirectResponse(url=settings.frontend_url)
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=JWT_EXPIRY_DAYS * 24 * 60 * 60,
    )
    response.delete_cookie("oauth_state")

    return response


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current authenticated user."""
    return current_user


@router.post("/logout")
async def logout(response: Response):
    """Logout the current user."""
    response = RedirectResponse(url=settings.frontend_url, status_code=303)
    response.delete_cookie("session_token")
    return response


@router.get("/connect")
async def connect_account(request: Request, current_user: User = Depends(get_current_user)):
    """Initiate OAuth flow to connect additional Gmail account."""
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=GmailService.SCOPES,
        redirect_uri=f"{settings.backend_url}/api/auth/connect/callback",
    )

    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )

    response = RedirectResponse(url=auth_url)
    response.set_cookie(
        key="connect_state",
        value=state,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=600,
    )

    return response


@router.get("/connect/callback")
async def connect_callback(
    request: Request,
    code: str,
    state: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Handle callback for connecting additional Gmail account."""
    stored_state = request.cookies.get("connect_state")
    if not stored_state or stored_state != state:
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=GmailService.SCOPES,
        redirect_uri=f"{settings.backend_url}/api/auth/connect/callback",
        state=state,
    )

    flow.fetch_token(code=code)
    credentials = flow.credentials

    async with httpx.AsyncClient() as client:
        response = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {credentials.token}"},
        )
        if response.status_code != 200:
            raise HTTPException(status_code=400, detail="Failed to get user info")
        user_info = response.json()

    email = user_info.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Email not provided")

    existing = (
        db.query(GmailAccount)
        .filter(GmailAccount.user_id == current_user.id, GmailAccount.email == email)
        .first()
    )

    encrypted_access = encrypt_token(credentials.token)
    encrypted_refresh = encrypt_token(credentials.refresh_token) if credentials.refresh_token else None

    if existing:
        existing.access_token = encrypted_access
        existing.refresh_token = encrypted_refresh or existing.refresh_token
        existing.token_expiry = credentials.expiry
    else:
        gmail_account = GmailAccount(
            user_id=current_user.id,
            email=email,
            access_token=encrypted_access,
            refresh_token=encrypted_refresh,
            token_expiry=credentials.expiry,
        )
        db.add(gmail_account)

    db.commit()

    response = RedirectResponse(url=settings.frontend_url)
    response.delete_cookie("connect_state")

    return response


@router.put("/settings")
async def update_user_settings(
    auto_sync_enabled: bool = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update user settings."""
    if auto_sync_enabled is not None:
        current_user.auto_sync_enabled = auto_sync_enabled
        db.commit()

    return {
        "auto_sync_enabled": current_user.auto_sync_enabled,
    }


@router.get("/sync-status")
async def get_sync_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get sync status for all connected accounts."""
    accounts = (
        db.query(GmailAccount)
        .filter(GmailAccount.user_id == current_user.id)
        .all()
    )

    # Get the most recent sync time across all accounts
    last_synced_at = None
    if accounts:
        synced_times = [acc.last_synced_at for acc in accounts if acc.last_synced_at]
        if synced_times:
            last_synced_at = max(synced_times)

    return {
        "auto_sync_enabled": current_user.auto_sync_enabled,
        "last_synced_at": f"{last_synced_at.isoformat()}Z" if last_synced_at else None,
        "accounts_count": len(accounts),
    }
