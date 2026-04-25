import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DEEPSEEK_API_KEY", "test-deepseek-key")
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret")
os.environ.setdefault("ADMIN_PASSWORD", "test123")
os.environ.setdefault("COZE_PLUGIN_TOKEN", "shunfa-coze-token")

from app.main import app
from app.database import Base
from app.dependencies import get_db
from app.config import settings

# In-memory SQLite for tests
TEST_DATABASE_URL = "sqlite://"


@pytest.fixture(scope="function")
def db_engine():
    engine = create_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def db(db_engine):
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=db_engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def client(db):
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def override_test_settings():
    original_admin_password = settings.admin_password
    original_coze_plugin_token = settings.coze_plugin_token
    original_environment = settings.environment

    settings.admin_password = "test123"
    settings.coze_plugin_token = "shunfa-coze-token"
    settings.environment = "test"

    try:
        yield
    finally:
        settings.admin_password = original_admin_password
        settings.coze_plugin_token = original_coze_plugin_token
        settings.environment = original_environment
