from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Boolean, LargeBinary
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(255))
    picture = Column(String(500))
    auto_sync_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    gmail_accounts = relationship("GmailAccount", back_populates="user", cascade="all, delete-orphan")
    categories = relationship("Category", back_populates="user", cascade="all, delete-orphan")


class GmailAccount(Base):
    __tablename__ = "gmail_accounts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    email = Column(String(255), nullable=False)
    access_token = Column(LargeBinary, nullable=False)
    refresh_token = Column(LargeBinary)
    token_expiry = Column(DateTime)
    last_synced_at = Column(DateTime)
    last_history_id = Column(String(50))  # For Gmail push notifications
    watch_expiration = Column(DateTime)  # When the Gmail watch expires
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="gmail_accounts")
    emails = relationship("Email", back_populates="gmail_account", cascade="all, delete-orphan")


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="categories")
    emails = relationship("Email", back_populates="category")


class Email(Base):
    __tablename__ = "emails"

    id = Column(Integer, primary_key=True, index=True)
    gmail_account_id = Column(Integer, ForeignKey("gmail_accounts.id"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)
    gmail_message_id = Column(String(255), nullable=False, index=True)
    thread_id = Column(String(255))
    subject = Column(String(500))
    sender = Column(String(255))
    sender_email = Column(String(255))
    received_at = Column(DateTime)
    body_text = Column(Text)
    body_html = Column(Text)
    ai_summary = Column(Text)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    gmail_account = relationship("GmailAccount", back_populates="emails")
    category = relationship("Category", back_populates="emails")
