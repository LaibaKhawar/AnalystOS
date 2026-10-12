from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.api.schemas import LoginIn, RegisterIn, TokenOut, UserOut
from app.core.config import get_settings
from app.core.errors import AnalystError, AuthError
from app.core.security import create_access_token, hash_password, verify_password
from app.db.models import User
from app.db.session import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=TokenOut, status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)) -> TokenOut:
    if not get_settings().allow_registration:
        raise AuthError("Registration is disabled on this deployment")
    email = body.email.lower()
    if db.query(User).filter(User.email == email).first():
        raise AnalystError("An account with this email already exists")
    is_first = db.query(User).count() == 0
    user = User(email=email, name=body.name.strip(), password_hash=hash_password(body.password), is_admin=is_first)
    db.add(user)
    db.commit()
    return TokenOut(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, db: Session = Depends(get_db)) -> TokenOut:
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise AuthError("Incorrect email or password")
    return TokenOut(access_token=create_access_token(user.id), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)) -> User:
    return user
