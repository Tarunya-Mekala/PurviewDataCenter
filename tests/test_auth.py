from fastapi import status
from app.core.config import settings


def test_superadmin_oauth2_login_success(unauth_client):
    res = unauth_client.post(
        "/api/v1/auth/login",
        data={
            "username": settings.SUPERADMIN_EMAIL,
            "password": settings.SUPERADMIN_PASSWORD,
        },
    )
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == settings.SUPERADMIN_EMAIL
    assert data["user"]["is_super_admin"] is True
    assert data["user"]["id"].startswith("usr_")


def test_superadmin_json_login_success(unauth_client):
    res = unauth_client.post(
        "/api/v1/auth/login/json",
        json={
            "email": settings.SUPERADMIN_EMAIL,
            "password": settings.SUPERADMIN_PASSWORD,
        },
    )
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert "access_token" in data
    assert data["user"]["email"] == settings.SUPERADMIN_EMAIL


def test_login_incorrect_password(unauth_client):
    res = unauth_client.post(
        "/api/v1/auth/login",
        data={
            "username": settings.SUPERADMIN_EMAIL,
            "password": "WrongPassword@123",
        },
    )
    assert res.status_code == status.HTTP_401_UNAUTHORIZED
    assert "Incorrect email or password" in res.json()["detail"]


def test_login_unknown_user(unauth_client):
    res = unauth_client.post(
        "/api/v1/auth/login",
        data={
            "username": "nonexistent@datacenter.ai",
            "password": "AnyPassword",
        },
    )
    assert res.status_code == status.HTTP_401_UNAUTHORIZED


def test_get_current_superadmin_profile(client):
    res = client.get("/api/v1/auth/me")
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert data["email"] == settings.SUPERADMIN_EMAIL
    assert data["is_super_admin"] is True


def test_unauthenticated_request_rejected(unauth_client):
    # Unauthenticated request to protected route
    res = unauth_client.get("/api/v1/projects")
    assert res.status_code == status.HTTP_401_UNAUTHORIZED
    assert res.json()["detail"] == "Not authenticated"


def test_invalid_token_rejected(unauth_client):
    res = unauth_client.get(
        "/api/v1/projects",
        headers={"Authorization": "Bearer invalid_jwt_token_123"},
    )
    assert res.status_code == status.HTTP_401_UNAUTHORIZED
