import pytest


def test_list_emails_empty(authenticated_client, test_gmail_account):
    response = authenticated_client.get("/api/emails")
    assert response.status_code == 200
    assert response.json() == []


def test_list_emails(authenticated_client, test_email):
    response = authenticated_client.get("/api/emails")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["subject"] == "Test Email"


def test_list_emails_by_category(authenticated_client, test_email, test_category):
    response = authenticated_client.get(
        f"/api/emails?category_id={test_category.id}"
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["category_id"] == test_category.id


def test_list_emails_wrong_category(authenticated_client, test_email):
    response = authenticated_client.get("/api/emails?category_id=99999")
    assert response.status_code == 200
    assert response.json() == []


def test_get_email_detail(authenticated_client, test_email):
    response = authenticated_client.get(f"/api/emails/{test_email.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["subject"] == "Test Email"
    assert data["body_text"] == "This is the email body text."
    assert data["ai_summary"] == "This is a test email summary."


def test_get_email_not_found(authenticated_client):
    response = authenticated_client.get("/api/emails/99999")
    assert response.status_code == 404


def test_list_uncategorized_emails(authenticated_client, db, test_gmail_account):
    from app.models import Email

    email = Email(
        gmail_account_id=test_gmail_account.id,
        category_id=None,
        gmail_message_id="msg_uncategorized",
        subject="Uncategorized Email",
        sender="sender@example.com",
    )
    db.add(email)
    db.commit()

    response = authenticated_client.get("/api/emails/uncategorized")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["subject"] == "Uncategorized Email"


def test_update_email_category(authenticated_client, test_email, db, test_user):
    from app.models import Category

    new_category = Category(
        user_id=test_user.id,
        name="New Category"
    )
    db.add(new_category)
    db.commit()

    response = authenticated_client.put(
        f"/api/emails/{test_email.id}/category?category_id={new_category.id}"
    )
    assert response.status_code == 200

    response = authenticated_client.get(f"/api/emails/{test_email.id}")
    assert response.json()["category_id"] == new_category.id


def test_emails_unauthenticated(client):
    response = client.get("/api/emails")
    assert response.status_code == 401


def test_email_includes_account_email(authenticated_client, test_email, test_gmail_account):
    """Email response should include the account_email field."""
    response = authenticated_client.get("/api/emails")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["account_email"] == test_gmail_account.email


def test_email_detail_includes_account_email(authenticated_client, test_email, test_gmail_account):
    """Email detail response should include the account_email field."""
    response = authenticated_client.get(f"/api/emails/{test_email.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["account_email"] == test_gmail_account.email
