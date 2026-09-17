from datetime import datetime
from typing import Optional

import bcrypt
from fastapi import Depends, Request
from sqlmodel import Session, select

from app.database import get_session
from app.models import User


MAX_PASSWORD_BYTES = 72  # bcrypt limit


class RequiresLogin(Exception):
    """Raised when a protected route is accessed without a valid session."""


# ---------- password hashing ----------

def hash_password(password: str) -> str:
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError("Password is too long.")
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"), password_hash.encode("utf-8")
        )
    except (ValueError, TypeError):
        return False


# ---------- session helpers ----------

def login_user(request: Request, user: User) -> None:
    request.session["user_id"] = user.id


def logout_user(request: Request) -> None:
    request.session.clear()


# ---------- current user dependencies ----------

def get_current_user_optional(
    request: Request,
    session: Session = Depends(get_session),
) -> Optional[User]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None

    user = session.get(User, user_id)
    if user is None:
        return None

    # Reset monthly usage counter if we crossed into a new month.
    # Doing it here guarantees the UI always reflects the current
    # period — even when the user only views the landing page or
    # the navbar without touching the upload flow.
    from app.limiter import ensure_usage_period
    ensure_usage_period(user, session)

    return user


def get_current_user(
    user: Optional[User] = Depends(get_current_user_optional),
) -> User:
    if user is None:
        raise RequiresLogin()
    return user


# ---------- user lookup ----------

def get_user_by_email(session: Session, email: str) -> Optional[User]:
    normalized = email.strip().lower()
    return session.exec(select(User).where(User.email == normalized)).first()


def utcnow() -> datetime:
    return datetime.utcnow()