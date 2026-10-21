from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    check_login_rate_limit,
    create_access_token,
    get_current_super_admin,
    hash_password,
    record_login_failure,
    reset_login_attempts,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    TokenResponse,
    UserCreate,
    UserListResponse,
    UserResponse,
    UserRole,
    UserUpdate,
)
from app.utils.id_generator import generate_id

router = APIRouter(prefix="/auth", tags=["Authentication"])

ALLOWED_ROLES = {role.value for role in UserRole}


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="User OAuth2 Login",
    description="Authenticate credentials using standard OAuth2 Form (compatible with Swagger UI 'Authorize' button).",
)
def login_oauth2(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    email = form_data.username.strip().lower()
    check_login_rate_limit(key=email)

    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.hashed_password):
        record_login_failure(key=email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated.",
        )

    if user.role not in ALLOWED_ROLES and not user.is_super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access restricted: unknown role '{user.role}'.",
        )

    reset_login_attempts(key=email)

    token_data = {
        "sub": user.id,
        "email": user.email,
        "role": user.role,
        "is_super_admin": user.is_super_admin,
    }
    access_token = create_access_token(data=token_data)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserResponse.model_validate(user),
    )


@router.post(
    "/login/json",
    response_model=TokenResponse,
    summary="User JSON Login",
    description="Alternative JSON body endpoint for web frontend clients.",
)
def login_json(
    login_data: LoginRequest,
    db: Session = Depends(get_db),
):
    email = login_data.email.strip().lower()
    check_login_rate_limit(key=email)

    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()

    if not user or not verify_password(login_data.password, user.hashed_password):
        record_login_failure(key=email)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated.",
        )

    if user.role not in ALLOWED_ROLES and not user.is_super_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access restricted: unknown role '{user.role}'.",
        )

    reset_login_attempts(key=email)

    token_data = {
        "sub": user.id,
        "email": user.email,
        "role": user.role,
        "is_super_admin": user.is_super_admin,
    }
    access_token = create_access_token(data=token_data)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserResponse.model_validate(user),
    )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user profile",
    description="Retrieve profile details of the currently authenticated user.",
)
def get_me(
    current_admin: User = Depends(get_current_super_admin),
):
    return UserResponse.model_validate(current_admin)


# ---------------------------------------------------------
# User Management Endpoints (Super Admin / Admin)
# ---------------------------------------------------------

@router.post(
    "/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user with role",
    description="Create an uploader, reviewer, viewer, or admin user account.",
)
def create_user(
    user_in: UserCreate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    email = user_in.email.strip().lower()
    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User with email '{email}' already exists.",
        )

    is_super = user_in.role == UserRole.SUPER_ADMIN
    new_user = User(
        id=generate_id("usr"),
        email=email,
        hashed_password=hash_password(user_in.password),
        full_name=user_in.full_name,
        role=user_in.role.value,
        is_active=True,
        is_super_admin=is_super,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return UserResponse.model_validate(new_user)


@router.get(
    "/users",
    response_model=UserListResponse,
    summary="List all users",
    description="Retrieve all registered user accounts with their assigned roles.",
)
def list_users(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    users = db.execute(select(User).order_by(User.created_at.desc())).scalars().all()
    return UserListResponse(
        total=len(users),
        items=[UserResponse.model_validate(u) for u in users],
    )


@router.patch(
    "/users/{user_id}",
    response_model=UserResponse,
    summary="Update a user",
    description="Update a user's role, active status, or password.",
)
def update_user(
    user_id: str,
    user_in: UserUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if user_in.full_name is not None:
        user.full_name = user_in.full_name
    if user_in.role is not None:
        user.role = user_in.role.value
        user.is_super_admin = user_in.role == UserRole.SUPER_ADMIN
    if user_in.is_active is not None:
        user.is_active = user_in.is_active
    if user_in.password:
        user.hashed_password = hash_password(user_in.password)

    db.commit()
    db.refresh(user)
    return UserResponse.model_validate(user)


@router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a user",
)
def delete_user(
    user_id: str,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    user = db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == current_admin.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete your own user account")

    db.delete(user)
    db.commit()
    return None
