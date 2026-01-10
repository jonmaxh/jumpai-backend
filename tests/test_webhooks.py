import pytest
import base64
import json


def test_webhook_rejects_invalid_token(client):
    """Webhook should reject requests with invalid verification token."""
    from app.config import get_settings
    settings = get_settings()

    # Only test if verification token is configured
    if settings.pubsub_verification_token:
        response = client.post(
            "/api/webhooks/gmail?token=invalid_token",
            json={"message": {"data": ""}}
        )
        assert response.status_code == 403


def test_webhook_accepts_empty_data(client):
    """Webhook should accept requests with no data (verification requests)."""
    response = client.post(
        "/api/webhooks/gmail",
        json={"message": {}}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_webhook_ignores_unknown_account(client):
    """Webhook should ignore notifications for unknown accounts."""
    data = {"emailAddress": "unknown@example.com", "historyId": "12345"}
    encoded_data = base64.urlsafe_b64encode(json.dumps(data).encode()).decode()

    response = client.post(
        "/api/webhooks/gmail",
        json={"message": {"data": encoded_data}}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"


def test_webhook_processes_known_account(client, test_gmail_account, test_user, db):
    """Webhook should process notifications for known accounts."""
    # Enable auto sync for user
    test_user.auto_sync_enabled = True
    db.commit()

    data = {"emailAddress": test_gmail_account.email, "historyId": "12345"}
    encoded_data = base64.urlsafe_b64encode(json.dumps(data).encode()).decode()

    response = client.post(
        "/api/webhooks/gmail",
        json={"message": {"data": encoded_data}}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "processing"


def test_webhook_respects_auto_sync_disabled(client, test_gmail_account, test_user, db):
    """Webhook should ignore notifications when auto sync is disabled."""
    # Disable auto sync for user
    test_user.auto_sync_enabled = False
    db.commit()

    data = {"emailAddress": test_gmail_account.email, "historyId": "12345"}
    encoded_data = base64.urlsafe_b64encode(json.dumps(data).encode()).decode()

    response = client.post(
        "/api/webhooks/gmail",
        json={"message": {"data": encoded_data}}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ignored"
    assert response.json()["reason"] == "auto sync disabled"


def test_webhook_rejects_invalid_json(client):
    """Webhook should reject invalid JSON body."""
    response = client.post(
        "/api/webhooks/gmail",
        content="not json",
        headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 400


def test_webhook_rejects_invalid_base64_data(client):
    """Webhook should reject invalid base64 data."""
    response = client.post(
        "/api/webhooks/gmail",
        json={"message": {"data": "not-valid-base64!!!"}}
    )
    assert response.status_code == 400
