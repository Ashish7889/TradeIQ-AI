import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models  # noqa: F401
from database import Base, get_db
from limiter import limiter
from main import app

# In-memory SQLite database for testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def setup_database():
    Base.metadata.create_all(bind=engine)
    app.dependency_overrides[get_db] = override_get_db
    limiter.enabled = False  # Disable rate limiter during tests
    yield
    Base.metadata.drop_all(bind=engine)
    app.dependency_overrides.clear()
    limiter.enabled = True


@pytest.fixture
def client():
    return TestClient(app)


def test_auth_flow(client):
    # 1. Sign up new user
    signup_payload = {"username": "trader_alice", "password": "supersecretpassword123"}
    resp = client.post("/api/auth/signup", json=signup_payload)
    assert resp.status_code == 200, resp.text
    token_data = resp.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"

    # 2. Duplicate signup should return 400
    resp_dup = client.post("/api/auth/signup", json=signup_payload)
    assert resp_dup.status_code == 400
    assert "already registered" in resp_dup.text

    # 3. Login with correct password
    login_resp = client.post(
        "/api/auth/login",
        data={"username": "trader_alice", "password": "supersecretpassword123"},
    )
    assert login_resp.status_code == 200
    access_token = login_resp.json()["access_token"]

    # 4. Login with wrong password
    bad_login = client.post(
        "/api/auth/login",
        data={"username": "trader_alice", "password": "wrongpassword"},
    )
    assert bad_login.status_code == 401

    # 5. Access authenticated endpoint (watchlist)
    headers = {"Authorization": f"Bearer {access_token}"}
    wl_resp = client.get("/api/watchlist", headers=headers)
    assert wl_resp.status_code == 200
    assert isinstance(wl_resp.json(), list)

    # 6. Add valid ticker to watchlist
    add_resp = client.post("/api/watchlist/add", json={"ticker": "AAPL"}, headers=headers)
    assert add_resp.status_code == 200

    # 7. Add invalid ticker to watchlist returns 422
    add_invalid = client.post("/api/watchlist/add", json={"ticker": "INVALID$$"}, headers=headers)
    assert add_invalid.status_code == 422

    # 8. User profile endpoint
    profile_resp = client.get("/api/user/profile", headers=headers)
    assert profile_resp.status_code == 200
    profile_data = profile_resp.json()
    assert profile_data["username"] == "trader_alice"
    assert profile_data["watchlist_count"] == 1
    assert "preferences" in profile_data

    # 9. Change password
    pwd_resp = client.post(
        "/api/user/change-password",
        json={"current_password": "supersecretpassword123", "new_password": "brandnewpassword999"},
        headers=headers,
    )
    assert pwd_resp.status_code == 200

    # 10. Login with new password
    new_login = client.post(
        "/api/auth/login",
        data={"username": "trader_alice", "password": "brandnewpassword999"},
    )
    assert new_login.status_code == 200


def test_endpoint_ticker_validation(client):
    # Test path ticker validation
    resp = client.get("/api/stock/INVALID$$/sentiment")
    assert resp.status_code == 422

