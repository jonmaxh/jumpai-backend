import pytest


def test_health_check(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_get_me_unauthenticated(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_get_me_authenticated(authenticated_client, test_user):
    response = authenticated_client.get("/api/auth/me")
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == test_user.email
    assert data["name"] == test_user.name


def test_google_auth_redirect(client):
    response = client.get("/api/auth/google", follow_redirects=False)
    assert response.status_code == 307
    assert "accounts.google.com" in response.headers["location"]


def test_logout(authenticated_client):
    response = authenticated_client.post("/api/auth/logout", follow_redirects=False)
    assert response.status_code == 303


def test_get_sync_status(authenticated_client, test_gmail_account):
    response = authenticated_client.get("/api/auth/sync-status")
    assert response.status_code == 200
    data = response.json()
    assert "auto_sync_enabled" in data
    assert "last_synced_at" in data
    assert "accounts_count" in data
    assert data["accounts_count"] == 1


def test_get_sync_status_no_accounts(authenticated_client):
    response = authenticated_client.get("/api/auth/sync-status")
    assert response.status_code == 200
    data = response.json()
    assert data["accounts_count"] == 0
    assert data["last_synced_at"] is None


def test_update_auto_sync_enabled(authenticated_client, test_user):
    # Disable auto sync
    response = authenticated_client.put("/api/auth/settings?auto_sync_enabled=false")
    assert response.status_code == 200
    assert response.json()["auto_sync_enabled"] is False

    # Enable auto sync
    response = authenticated_client.put("/api/auth/settings?auto_sync_enabled=true")
    assert response.status_code == 200
    assert response.json()["auto_sync_enabled"] is True


def test_sync_status_returns_utc_timestamp(authenticated_client, test_gmail_account, db):
    from datetime import datetime
    # Update last_synced_at
    test_gmail_account.last_synced_at = datetime.utcnow()
    db.commit()

    response = authenticated_client.get("/api/auth/sync-status")
    assert response.status_code == 200
    data = response.json()
    # Should end with Z to indicate UTC
    assert data["last_synced_at"].endswith("Z")
