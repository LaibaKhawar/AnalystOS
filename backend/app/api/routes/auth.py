from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.api.schemas import LoginIn, RefreshIn, RegisterIn, TokenOut, UserOut
from app.core.config import get_settings
from app.core.errors import AnalystError, AuthError
from app.core.ratelimit import hit
from app.core.security import create_access_token, hash_password, hash_token, new_refresh_token, verify_password
from app.db.models import RefreshToken, User
from app.db.session import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


def issue_tokens(db: Session, user: User) -> TokenOut:
    token, digest = new_refresh_token()
    expires = datetime.now(UTC) + timedelta(days=get_settings().refresh_token_ttl_days)
    db.add(RefreshToken(user_id=user.id, token_hash=digest, expires_at=expires))
    db.commit()
    return TokenOut(access_token=create_access_token(user.id), refresh_token=token, user=UserOut.model_validate(user))


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")


@router.post("/register", response_model=TokenOut, status_code=201)
def register(body: RegisterIn, request: Request, db: Session = Depends(get_db)) -> TokenOut:
    hit(f"register:{_client_ip(request)}", get_settings().login_rate_per_minute, 60)
    if not get_settings().allow_registration:
        raise AuthError("Registration is disabled on this deployment")
    email = body.email.lower()
    if db.query(User).filter(User.email == email).first():
        raise AnalystError("An account with this email already exists")
    is_first = db.query(User).count() == 0
    user = User(
        email=email,
        name=body.name.strip(),
        password_hash=hash_password(body.password),
        is_admin=is_first,
        role="admin" if is_first else "analyst",
    )
    db.add(user)
    db.commit()
    return issue_tokens(db, user)


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, db: Session = Depends(get_db)) -> TokenOut:
    hit(f"login:{_client_ip(request)}", get_settings().login_rate_per_minute, 60)
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise AuthError("Incorrect email or password")
    return issue_tokens(db, user)


@router.post("/refresh", response_model=TokenOut)
def refresh(body: RefreshIn, db: Session = Depends(get_db)) -> TokenOut:
    """Rotate a refresh token. Reusing a revoked token revokes every session of that user (theft signal)."""
    record = db.query(RefreshToken).filter(RefreshToken.token_hash == hash_token(body.refresh_token)).first()
    now = datetime.now(UTC)
    if record is None:
        raise AuthError("Session expired, please sign in again")
    if record.revoked_at is not None:
        db.query(RefreshToken).filter(RefreshToken.user_id == record.user_id, RefreshToken.revoked_at.is_(None)).update(
            {"revoked_at": now}
        )
        db.commit()
        raise AuthError("Session expired, please sign in again")
    if record.expires_at < now:
        raise AuthError("Session expired, please sign in again")
    user = db.get(User, record.user_id)
    if user is None:
        raise AuthError("Account not found")
    record.revoked_at = now
    return issue_tokens(db, user)


@router.post("/logout", status_code=204)
def logout(body: RefreshIn, db: Session = Depends(get_db)) -> None:
    record = db.query(RefreshToken).filter(RefreshToken.token_hash == hash_token(body.refresh_token)).first()
    if record is not None and record.revoked_at is None:
        record.revoked_at = datetime.now(UTC)
        db.commit()


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)) -> User:
    return user
