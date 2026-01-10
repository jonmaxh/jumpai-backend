import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta


def test_list_accounts(authenticated_client, test_gmail_account):
    response = authenticated_client.get("/api/accounts")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["email"] == test_gmail_account.email


def test_list_accounts_empty(authenticated_client):
    response = authenticated_client.get("/api/accounts")
    assert response.status_code == 200
    assert response.json() == []


def test_list_accounts_unauthenticated(client):
    response = client.get("/api/accounts")
    assert response.status_code == 401


def test_get_watch_status_no_watch(authenticated_client, test_gmail_account):
    response = authenticated_client.get(f"/api/accounts/{test_gmail_account.id}/watch")
    assert response.status_code == 200
    data = response.json()
    assert data["watch_active"] is False
    assert data["watch_expiration"] is None


def test_get_watch_status_active(authenticated_client, test_gmail_account, db):
    # Set watch expiration in the future
    test_gmail_account.watch_expiration = datetime.utcnow() + timedelta(days=1)
    test_gmail_account.last_history_id = "12345"
    db.commit()

    response = authenticated_client.get(f"/api/accounts/{test_gmail_account.id}/watch")
    assert response.status_code == 200
    data = response.json()
    assert data["watch_active"] is True
    assert data["last_history_id"] == "12345"


def test_get_watch_status_expired(authenticated_client, test_gmail_account, db):
    # Set watch expiration in the past
    test_gmail_account.watch_expiration = datetime.utcnow() - timedelta(hours=1)
    db.commit()

    response = authenticated_client.get(f"/api/accounts/{test_gmail_account.id}/watch")
    assert response.status_code == 200
    data = response.json()
    assert data["watch_active"] is False


def test_get_watch_status_not_found(authenticated_client):
    response = authenticated_client.get("/api/accounts/99999/watch")
    assert response.status_code == 404


def test_enable_watch_not_configured(authenticated_client, test_gmail_account):
    """Should fail when Pub/Sub is not configured."""
    response = authenticated_client.post(f"/api/accounts/{test_gmail_account.id}/watch")
    assert response.status_code == 400
    assert "not configured" in response.json()["detail"].lower()


@patch('app.routers.accounts.settings')
@patch('app.routers.accounts.GmailService')
def test_enable_watch_success(mock_gmail, mock_settings, authenticated_client, test_gmail_account):
    """Should enable watch when properly configured."""
    mock_settings.push_notifications_enabled = True
    mock_settings.pubsub_topic = "projects/test/topics/gmail"

    mock_service = MagicMock()
    mock_service.watch.return_value = {
        "history_id": "12345",
        "expiration": str(int((datetime.utcnow() + timedelta(days=7)).timestamp() * 1000))
    }
    mock_gmail.return_value = mock_service

    response = authenticated_client.post(f"/api/accounts/{test_gmail_account.id}/watch")
    assert response.status_code == 200
    data = response.json()
    assert data["message"] == "Push notifications enabled"
    assert data["history_id"] == "12345"


@patch('app.routers.accounts.GmailService')
def test_disable_watch(mock_gmail, authenticated_client, test_gmail_account, db):
    """Should disable watch."""
    test_gmail_account.watch_expiration = datetime.utcnow() + timedelta(days=1)
    db.commit()

    mock_service = MagicMock()
    mock_service.stop_watch.return_value = True
    mock_gmail.return_value = mock_service

    response = authenticated_client.delete(f"/api/accounts/{test_gmail_account.id}/watch")
    assert response.status_code == 200
    assert response.json()["message"] == "Push notifications disabled"
