from __future__ import annotations

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.errors import AuthError, NotFoundError
from app.core.logging import user_id_var
from app.core.security import decode_access_token
from app.db.models import Analysis, Conversation, DataSource, User
from app.db.session import get_db


def current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthError("Sign in to continue")
    user = db.get(User, decode_access_token(authorization.split(" ", 1)[1].strip()))
    if user is None:
        raise AuthError("Account not found")
    user_id_var.set(user.id)
    return user


def owned_source(db: Session, user: User, source_id: str) -> DataSource:
    source = db.get(DataSource, source_id)
    if source is None or source.user_id != user.id:
        raise NotFoundError("Data source not found")
    return source


def owned_conversation(db: Session, user: User, conversation_id: str) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None or conversation.user_id != user.id:
        raise NotFoundError("Conversation not found")
    return conversation


def owned_analysis(db: Session, user: User, analysis_id: str) -> Analysis:
    analysis = db.get(Analysis, analysis_id)
    if analysis is None or analysis.user_id != user.id:
        raise NotFoundError("Analysis not found")
    return analysis
