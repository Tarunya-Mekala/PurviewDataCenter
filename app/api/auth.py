from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    create_access_token,
    get_current_super_admin,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Super Admin OAuth2 Login",
    description="Authenticate Super Admin credentials using standard OAuth2 Form (compatible with Swagger UI 'Authorize' button).",
)
def login_oauth2(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    email = form_data.username.strip().lower()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin account is deactivated.",
        )

    if not user.is_super_admin and user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access restricted to Super Admin accounts.",
        )

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
    summary="Super Admin JSON Login",
    description="Alternative JSON body endpoint for web frontend clients.",
)
def login_json(
    login_data: LoginRequest,
    db: Session = Depends(get_db),
):
    email = login_data.email.strip().lower()
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()

    if not user or not verify_password(login_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super admin account is deactivated.",
        )

    if not user.is_super_admin and user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access restricted to Super Admin accounts.",
        )

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
    summary="Get current Super Admin profile",
    description="Retrieve profile details of the currently authenticated Super Admin.",
)
def get_me(
    current_admin: User = Depends(get_current_super_admin),
):
    return UserResponse.model_validate(current_admin)
