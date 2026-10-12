from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, id_column


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[str] = id_column("usr")
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(default=False)
    # admin: everything, incl. user roles | analyst: upload, connect, ask, schedule | viewer: read-only
    role: Mapped[str] = mapped_column(String(16), default="analyst", server_default="analyst")


class RefreshToken(TimestampMixin, Base):
    """Long-lived refresh tokens, stored hashed and rotated on every use."""

    __tablename__ = "refresh_tokens"

    id: Mapped[str] = id_column("rft")
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
