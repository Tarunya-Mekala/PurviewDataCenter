import os
import tempfile
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.database import Base, get_db
from app.core.security import create_access_token, init_super_admin
import app.models  # noqa: F401
from app.main import app


@pytest.fixture(scope="session")
def test_upload_dir():
    with tempfile.TemporaryDirectory() as tmp:
        orig_upload = settings.UPLOAD_DIR
        settings.UPLOAD_DIR = tmp
        yield tmp
        settings.UPLOAD_DIR = orig_upload


@pytest.fixture(scope="session")
def test_engine():
    # In-memory SQLite with StaticPool so all threads share the exact same DB
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    import app.core.database
    orig_session_local = app.core.database.SessionLocal
    app.core.database.SessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=engine
    )
    yield engine
    app.core.database.SessionLocal = orig_session_local
    engine.dispose()


@pytest.fixture
def db_session(test_engine):
    TestingSessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=test_engine
    )
    session = TestingSessionLocal()
    # Seed super admin for testing
    init_super_admin(session)
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def superadmin_user(db_session):
    return init_super_admin(db_session)


@pytest.fixture
def auth_token(superadmin_user):
    return create_access_token(
        data={
            "sub": superadmin_user.id,
            "email": superadmin_user.email,
            "role": superadmin_user.role,
            "is_super_admin": True,
        }
    )


@pytest.fixture
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture
def client(test_engine, db_session, test_upload_dir, auth_headers):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        # Pre-configure client with authorization headers by default
        test_client.headers.update(auth_headers)
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def unauth_client(test_engine, db_session, test_upload_dir):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
