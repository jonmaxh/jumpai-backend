import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import User, GmailAccount, Category, Email
from app.utils import encrypt_token


TEST_DATABASE_URL = "sqlite:///:memory:"

engine = create_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="function")
def db():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client(db):
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def test_user(db):
    user = User(
        email="test@example.com",
        name="Test User",
        picture="https://example.com/picture.jpg"
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def test_gmail_account(db, test_user):
    account = GmailAccount(
        user_id=test_user.id,
        email="test@example.com",
        access_token=encrypt_token("test_access_token"),
        refresh_token=encrypt_token("test_refresh_token"),
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


@pytest.fixture
def test_category(db, test_user):
    category = Category(
        user_id=test_user.id,
        name="Test Category",
        description="A test category for emails"
    )
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@pytest.fixture
def test_email(db, test_gmail_account, test_category):
    email = Email(
        gmail_account_id=test_gmail_account.id,
        category_id=test_category.id,
        gmail_message_id="msg_123",
        thread_id="thread_123",
        subject="Test Email",
        sender="Sender Name",
        sender_email="sender@example.com",
        body_text="This is the email body text.",
        body_html="<p>This is the email body.</p>",
        ai_summary="This is a test email summary.",
    )
    db.add(email)
    db.commit()
    db.refresh(email)
    return email


@pytest.fixture
def authenticated_client(client, test_user, db, monkeypatch):
    from jose import jwt
    from app.config import get_settings

    settings = get_settings()
    token = jwt.encode(
        {"sub": str(test_user.id)},
        settings.secret_key,
        algorithm="HS256"
    )

    client.cookies.set("session_token", token)
    return client
