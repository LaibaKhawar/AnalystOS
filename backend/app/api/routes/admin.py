"""User administration (admins only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import current_user, require_role
from app.api.schemas import RoleIn, UserOut
from app.core.errors import NotFoundError, ValidationFailed
from app.db.models import User
from app.db.session import get_db

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users", response_model=list[UserOut])
def users(user: User = Depends(current_user), db: Session = Depends(get_db)) -> list[User]:
    require_role(user, "admin")
    return db.query(User).order_by(User.created_at).all()


@router.patch("/users/{user_id}/role", response_model=UserOut)
def set_role(user_id: str, body: RoleIn, user: User = Depends(current_user), db: Session = Depends(get_db)) -> User:
    require_role(user, "admin")
    target = db.get(User, user_id)
    if target is None:
        raise NotFoundError("User not found")
    if target.id == user.id and body.role != "admin":
        raise ValidationFailed("Admins cannot remove their own admin role")
    target.role = body.role
    target.is_admin = body.role == "admin"
    db.commit()
    return target
