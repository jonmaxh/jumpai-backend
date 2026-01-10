from cryptography.fernet import Fernet
from app.config import get_settings
import base64
import hashlib

settings = get_settings()


def get_encryption_key() -> bytes:
    key = hashlib.sha256(settings.secret_key.encode()).digest()
    return base64.urlsafe_b64encode(key)


def encrypt_token(token: str) -> bytes:
    if not token:
        return b""
    fernet = Fernet(get_encryption_key())
    return fernet.encrypt(token.encode())


def decrypt_token(encrypted: bytes) -> str:
    if not encrypted:
        return ""
    fernet = Fernet(get_encryption_key())
    return fernet.decrypt(encrypted).decode()
