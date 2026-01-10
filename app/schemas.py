from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional


class UserBase(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    picture: Optional[str] = None


class UserCreate(UserBase):
    pass


class UserResponse(UserBase):
    id: int
    auto_sync_enabled: bool = True
    created_at: datetime

    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    auto_sync_enabled: Optional[bool] = None


class GmailAccountBase(BaseModel):
    email: EmailStr


class GmailAccountResponse(GmailAccountBase):
    id: int
    last_synced_at: Optional[datetime] = None
    created_at: datetime

    class Config:
        from_attributes = True


class CategoryBase(BaseModel):
    name: str
    description: Optional[str] = None


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


class CategoryResponse(CategoryBase):
    id: int
    user_id: int
    created_at: datetime
    email_count: Optional[int] = 0

    class Config:
        from_attributes = True


class EmailBase(BaseModel):
    subject: Optional[str] = None
    sender: Optional[str] = None
    sender_email: Optional[str] = None


class EmailResponse(EmailBase):
    id: int
    gmail_account_id: int
    account_email: Optional[str] = None  # The connected Gmail account this email belongs to
    category_id: Optional[int] = None
    gmail_message_id: str
    received_at: Optional[datetime] = None
    ai_summary: Optional[str] = None
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True


class EmailDetailResponse(EmailResponse):
    body_text: Optional[str] = None
    body_html: Optional[str] = None
    thread_id: Optional[str] = None


class BulkEmailAction(BaseModel):
    email_ids: list[int]


class UnsubscribeResult(BaseModel):
    email_id: int
    success: bool
    message: str


class CategoryBreakdown(BaseModel):
    category_id: Optional[int] = None
    category_name: str
    count: int


class SyncResponse(BaseModel):
    synced_count: int
    categorized_count: int
    uncategorized_count: int
    archived_count: int
    category_breakdown: list[CategoryBreakdown] = []
    last_synced_at: Optional[datetime] = None
