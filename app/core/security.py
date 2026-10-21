from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def hash_password(password: str) -> str:
    """Hash password using bcrypt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against bcrypt hash."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        return False


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Create a signed JWT access token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    return jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> dict:
    """Decode and validate a JWT access token."""
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI dependency to extract current authenticated user."""
    payload = decode_access_token(token)
    user_id: Optional[str] = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User associated with token not found.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated.",
        )

    return user


get_current_active_user = get_current_user


def require_roles(allowed_roles: list[str]):
    """FastAPI dependency to enforce fine-grained role-based access control."""
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.is_super_admin or current_user.role in ["super_admin", "admin"]:
            return current_user
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access forbidden: role '{current_user.role}' lacks permission for this action.",
            )
        return current_user
    return role_checker


def get_current_super_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """FastAPI dependency ensuring the caller has super admin privileges."""
    if not current_user.is_super_admin and current_user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Super Admin privileges required.",
        )
    return current_user


def get_current_user_flexible(
    token_param: Optional[str] = Query(None, alias="token"),
    bearer_token: Optional[str] = Depends(oauth2_scheme_optional),
    db: Session = Depends(get_db),
) -> User:
    """Accept token from Bearer Authorization header or ?token= query parameter."""
    raw_token = bearer_token or token_param
    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_access_token(raw_token)
    user_id: Optional[str] = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User associated with token not found.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated.",
        )

    return user


def get_current_super_admin_flexible(
    current_user: User = Depends(get_current_user_flexible),
) -> User:
    """Super Admin dependency supporting both Bearer header and ?token= query parameter."""
    if not current_user.is_super_admin and current_user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access forbidden: Super Admin privileges required.",
        )
    return current_user


def create_evidence_token(document_id: str, expires_minutes: int = 15) -> str:
    """Generate a short-lived signed token for secure document evidence image access."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    payload = {"doc_id": document_id, "exp": expire, "type": "evidence"}
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def verify_evidence_token(token: str) -> str:
    """Validate evidence token and return document_id."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        doc_id = payload.get("doc_id")
        if not doc_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid evidence token payload")
        return doc_id
    except (jwt.ExpiredSignatureError, jwt.PyJWTError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Expired or invalid evidence token")


# In-memory login rate limiter: {ip/email: [timestamp, ...]}
_login_attempts: dict = {}


def check_login_rate_limit(key: str, max_attempts: int = 5, window_seconds: int = 300) -> None:
    now = datetime.now(timezone.utc).timestamp()
    attempts = _login_attempts.get(key, [])
    attempts = [t for t in attempts if now - t < window_seconds]
    if len(attempts) >= max_attempts:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Please wait 5 minutes before trying again.",
        )


def record_login_failure(key: str, window_seconds: int = 300) -> None:
    now = datetime.now(timezone.utc).timestamp()
    attempts = _login_attempts.get(key, [])
    attempts = [t for t in attempts if now - t < window_seconds]
    attempts.append(now)
    _login_attempts[key] = attempts


def reset_login_attempts(key: str) -> None:
    _login_attempts.pop(key, None)


def init_super_admin(db: Session) -> User:
    """Ensure at least one super admin exists in the database on startup and sync password."""
    admin = db.execute(
        select(User).where(User.email == settings.SUPERADMIN_EMAIL)
    ).scalar_one_or_none()

    if not admin:
        admin = User(
            email=settings.SUPERADMIN_EMAIL,
            hashed_password=hash_password(settings.SUPERADMIN_PASSWORD),
            full_name=settings.SUPERADMIN_NAME,
            role="super_admin",
            is_active=True,
            is_super_admin=True,
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
    else:
        # Sync password to latest environment setting
        admin.hashed_password = hash_password(settings.SUPERADMIN_PASSWORD)
        db.commit()
        db.refresh(admin)

    return admin

