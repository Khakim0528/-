import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from ..deps import DB, CurrentUser
from ..mailer import send_verification_code
from ..models import EmailVerification, User
from ..schemas import ResendCodeIn, Token, UserCreate, UserOut, UserUpdate, VerifyEmailIn
from ..security import create_access_token, hash_password, verify_password

router = APIRouter(tags=["auth"])

CODE_TTL_MINUTES = 15
MAX_ATTEMPTS = 5
NOT_VERIFIED_MESSAGE = "Email не подтверждён. Введите код, отправленный на почту."


def _as_utc(dt: datetime) -> datetime:
    """SQLite drops tzinfo on round-trip even for `DateTime(timezone=True)` columns,
    so a value read back from it compares naive vs. aware and raises. Postgres
    doesn't have this issue, but treating a naive value as UTC there too is correct."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _issue_verification_code(db: DB, user: User) -> None:
    code = f"{secrets.randbelow(1_000_000):06d}"
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=CODE_TTL_MINUTES)
    record = db.scalar(select(EmailVerification).where(EmailVerification.user_id == user.id))
    if record:
        record.code, record.expires_at, record.attempts = code, expires_at, 0
    else:
        db.add(EmailVerification(user_id=user.id, code=code, expires_at=expires_at))
    db.commit()
    send_verification_code(user.email, code)


@router.post("/auth/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(data: UserCreate, db: DB):
    email = data.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    user = User(email=email, password_hash=hash_password(data.password),
                full_name=data.full_name, phone=data.phone)
    db.add(user)
    db.commit()
    _issue_verification_code(db, user)
    return user


@router.post("/auth/verify-email", response_model=Token)
def verify_email(data: VerifyEmailIn, db: DB):
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")
    if user.email_verified:
        return Token(access_token=create_access_token(user.id))

    record = db.scalar(select(EmailVerification).where(EmailVerification.user_id == user.id))
    if not record or _as_utc(record.expires_at) < datetime.now(timezone.utc):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Код истёк или ещё не запрошен. Отправьте его заново.")
    if record.attempts >= MAX_ATTEMPTS:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Слишком много попыток. Запросите новый код.")
    if record.code != data.code.strip():
        record.attempts += 1
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Неверный код")

    user.email_verified = True
    db.delete(record)
    db.commit()
    return Token(access_token=create_access_token(user.id))


@router.post("/auth/resend-code", status_code=status.HTTP_204_NO_CONTENT)
def resend_code(data: ResendCodeIn, db: DB):
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    if user and not user.email_verified:
        _issue_verification_code(db, user)
    # Same response whether or not the email is registered/already verified,
    # so this endpoint can't be used to check which emails exist.


@router.post("/auth/login", response_model=Token)
def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DB):
    """OAuth2 password flow: `username` is the email."""
    user = db.scalar(select(User).where(User.email == form.username.lower()))
    if not user or not user.is_active or not verify_password(form.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    if not user.email_verified:
        raise HTTPException(status.HTTP_403_FORBIDDEN, NOT_VERIFIED_MESSAGE)
    return Token(access_token=create_access_token(user.id))


@router.get("/users/me", response_model=UserOut)
def me(user: CurrentUser):
    return user


@router.patch("/users/me", response_model=UserOut)
def update_me(data: UserUpdate, user: CurrentUser, db: DB):
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    db.commit()
    return user
