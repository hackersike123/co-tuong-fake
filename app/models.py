"""Persistent account models."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, false, func
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


class User(Base):
    """A registered player account."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(512))
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class UserSession(Base):
    """A remembered device session; only a hash of the refresh token is stored."""

    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    refresh_token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class EmailVerificationOTP(Base):
    """Short-lived, one-time email activation code stored as a salted hash."""

    __tablename__ = "email_verification_otps"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    salt: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")


class Match(Base):
    """A completed room game and its replayable coordinate notation."""

    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    room_id: Mapped[int] = mapped_column(nullable=False, index=True)
    room_uuid: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    round_number: Mapped[int] = mapped_column(nullable=False)
    room_name: Mapped[str] = mapped_column(String(80), nullable=False)
    red_player: Mapped[str] = mapped_column(String(80), nullable=False)
    black_player: Mapped[str] = mapped_column(String(80), nullable=False)
    result: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(40))
    winner: Mapped[str | None] = mapped_column(String(1))
    notation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    final_fen: Mapped[str] = mapped_column(Text, nullable=False)
    finished_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
