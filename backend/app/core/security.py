"""Security, password hashing, and JWT utilities."""

import base64
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Union
import bcrypt
from cryptography.fernet import Fernet
from jose import JWTError, jwt
from app.core.config import settings


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a raw password against the stored bcrypt hash."""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        hashed_password.encode("utf-8"),
    )


def get_password_hash(password: str) -> str:
    """Generate a bcrypt password hash."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def create_access_token(
    subject: Union[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a signed JWT access token."""
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(
        to_encode,
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    return encoded_jwt


def decode_access_token(token: str) -> Optional[dict]:
    """Decode and validate a JWT access token."""
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
        return payload
    except JWTError:
        return None


def get_encryption_cipher() -> Fernet:
    """Derive a reproducible 32-byte Fernet key from the application secret key."""
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    return Fernet(key)


def encrypt_oauth_token(token: str) -> str:
    """Encrypt OAuth access or refresh token before persisting to database."""
    if not token:
        return ""
    cipher = get_encryption_cipher()
    return cipher.encrypt(token.encode("utf-8")).decode("utf-8")


def decrypt_oauth_token(encrypted_token: str) -> str:
    """Decrypt OAuth token for live API requests."""
    if not encrypted_token:
        return ""
    try:
        cipher = get_encryption_cipher()
        return cipher.decrypt(encrypted_token.encode("utf-8")).decode("utf-8")
    except Exception:
        # Fallback if raw or invalid token
        return encrypted_token

