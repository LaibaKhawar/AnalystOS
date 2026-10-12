from __future__ import annotations

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.errors import AuthError, ForbiddenError, NotFoundError
from app.core.logging import user_id_var
from app.core.security import decode_access_token
from app.db.models import Analysis, Conversation, DataSource, SourceShare, User
from app.db.session import get_db


def current_user(authorization: str | None = Header(default=None), db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthError("Sign in to continue")
    user = db.get(User, decode_access_token(authorization.split(" ", 1)[1].strip()))
    if user is None:
        raise AuthError("Account not found")
    user_id_var.set(user.id)
    return user


ACCESS_LEVELS = {"read": 0, "ask": 1, "manage": 2}


def source_access(db: Session, user: User, source: DataSource) -> str | None:
    """Effective access to a source: 'manage' (owner/admin), 'ask', 'read', or None."""
    if source.user_id == user.id or user.role == "admin":
        return "manage"
    share = (
        db.query(SourceShare).filter(SourceShare.data_source_id == source.id, SourceShare.user_id == user.id).first()
    )
    if share is None:
        return None
    level = "ask" if share.role == "analyst" else "read"
    return "read" if user.role == "viewer" else level


def owned_source(db: Session, user: User, source_id: str, need: str = "read") -> DataSource:
    """Load a source the user may access at the needed level. Unknown and unshared sources look the same (404)."""
    source = db.get(DataSource, source_id)
    access = source_access(db, user, source) if source is not None else None
    if source is None or access is None:
        raise NotFoundError("Data source not found")
    if ACCESS_LEVELS[access] < ACCESS_LEVELS[need]:
        raise ForbiddenError(
            "You have read-only access to this data source"
            if need == "ask"
            else "Only the owner of this data source can change it"
        )
    return source


def require_role(user: User, *roles: str) -> None:
    if user.role not in roles:
        raise ForbiddenError(f"This action needs one of these roles: {', '.join(roles)}")


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
