"""Password hashing, JWT issuing, and symmetric encryption for stored credentials."""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings
from app.core.errors import AuthError

_hasher = PasswordHasher()
_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def create_access_token(user_id: str) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_ttl_minutes),
        "typ": "access",
    }
    return jwt.encode(payload, settings.secret_key, algorithm=_ALGORITHM)


def new_refresh_token() -> tuple[str, str]:
    """Return (opaque token for the client, sha256 hash to store)."""
    token = secrets.token_urlsafe(48)
    return token, hash_token(token)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def decode_access_token(token: str) -> str:
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=[_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise AuthError("Invalid or expired session") from exc
    if payload.get("typ") != "access" or not payload.get("sub"):
        raise AuthError("Invalid session token")
    return str(payload["sub"])


def _fernet() -> Fernet:
    return Fernet(get_settings().encryption_key.encode())


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except InvalidToken as exc:
        raise AuthError("Stored credential could not be decrypted; re-enter the connection password") from exc
