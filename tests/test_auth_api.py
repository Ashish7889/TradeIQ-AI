import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models  # noqa: F401
import schemas
from app.config import Settings
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


def test_unauthorized_endpoints(client):
    # Endpoints requiring authentication should return 401 without auth header
    unauth_cases = [
        ("GET", "/api/watchlist"),
        ("GET", "/api/user/profile"),
        ("GET", "/api/preferences"),
        ("POST", "/api/user/change-password"),
        ("POST", "/api/report/generate"),
        ("GET", "/api/stock/AAPL/recommendation"),
        ("GET", "/api/stock/AAPL/langchain-analysis"),
    ]
    for method, path in unauth_cases:
        if method == "GET":
            resp = client.get(path)
        else:
            resp = client.post(path, json={})
        assert resp.status_code == 401, f"{method} {path} did not return 401 (got {resp.status_code})"

    # Invalid / forged bearer token should also return 401
    bad_headers = {"Authorization": "Bearer forged.invalid.token"}
    resp = client.get("/api/watchlist", headers=bad_headers)
    assert resp.status_code == 401


def test_watchlist_crud_and_cross_user_isolation(client):
    # Register user 1
    resp1 = client.post("/api/auth/signup", json={"username": "user_one", "password": "password1234"})
    assert resp1.status_code == 200
    token1 = resp1.json()["access_token"]
    h1 = {"Authorization": f"Bearer {token1}"}

    # Register user 2
    resp2 = client.post("/api/auth/signup", json={"username": "user_two", "password": "password1234"})
    assert resp2.status_code == 200
    token2 = resp2.json()["access_token"]
    h2 = {"Authorization": f"Bearer {token2}"}

    # User 1 adds AAPL and MSFT
    assert client.post("/api/watchlist/add", json={"ticker": "AAPL"}, headers=h1).status_code == 200
    assert client.post("/api/watchlist/add", json={"ticker": "MSFT"}, headers=h1).status_code == 200

    # User 2 watchlist should be empty (cross-user isolation)
    wl2 = client.get("/api/watchlist", headers=h2).json()
    assert len(wl2) == 0

    # User 2 adds GOOGL
    assert client.post("/api/watchlist/add", json={"ticker": "GOOGL"}, headers=h2).status_code == 200

    # Verify User 1 sees AAPL and MSFT, not GOOGL
    wl1 = client.get("/api/watchlist", headers=h1).json()
    tickers1 = [item["ticker"] for item in wl1]
    assert "AAPL" in tickers1
    assert "MSFT" in tickers1
    assert "GOOGL" not in tickers1

    # User 1 deletes AAPL
    del_resp = client.delete("/api/watchlist/AAPL", headers=h1)
    assert del_resp.status_code == 200

    wl1_after = client.get("/api/watchlist", headers=h1).json()
    tickers1_after = [item["ticker"] for item in wl1_after]
    assert "AAPL" not in tickers1_after
    assert "MSFT" in tickers1_after

    # User 1 deletes non-existent ticker returns 404
    assert client.delete("/api/watchlist/TSLA", headers=h1).status_code == 404

    # User 2 still has GOOGL unaffected
    wl2_check = client.get("/api/watchlist", headers=h2).json()
    assert [item["ticker"] for item in wl2_check] == ["GOOGL"]

    # User 1 clears their watchlist
    clear_resp = client.delete("/api/watchlist", headers=h1)
    assert clear_resp.status_code == 200
    assert len(client.get("/api/watchlist", headers=h1).json()) == 0

    # User 2's watchlist remains intact
    assert len(client.get("/api/watchlist", headers=h2).json()) == 1


def test_change_password_validation(client):
    # Register user
    signup_resp = client.post("/api/auth/signup", json={"username": "pwd_tester", "password": "initialPassword123"})
    assert signup_resp.status_code == 200
    token = signup_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Wrong current password returns 400
    resp_wrong = client.post(
        "/api/user/change-password",
        json={"current_password": "wrongpassword123", "new_password": "newpassword1234"},
        headers=headers,
    )
    assert resp_wrong.status_code == 400

    # 2. New password too short (< 8 chars) returns 422
    resp_short = client.post(
        "/api/user/change-password",
        json={"current_password": "initialPassword123", "new_password": "short"},
        headers=headers,
    )
    assert resp_short.status_code == 422

    # 3. New password too long (> 128 chars) returns 422
    resp_long = client.post(
        "/api/user/change-password",
        json={"current_password": "initialPassword123", "new_password": "a" * 129},
        headers=headers,
    )
    assert resp_long.status_code == 422

    # 4. Valid password change returns 200
    resp_success = client.post(
        "/api/user/change-password",
        json={"current_password": "initialPassword123", "new_password": "newSuperPassword456"},
        headers=headers,
    )
    assert resp_success.status_code == 200

    # 5. Old password no longer authenticates
    old_login = client.post(
        "/api/auth/login",
        data={"username": "pwd_tester", "password": "initialPassword123"},
    )
    assert old_login.status_code == 401

    # 6. New password authenticates successfully
    new_login = client.post(
        "/api/auth/login",
        data={"username": "pwd_tester", "password": "newSuperPassword456"},
    )
    assert new_login.status_code == 200


def test_input_max_length_constraints(client):
    # Signup password exceeding 128 characters returns 422
    resp = client.post(
        "/api/auth/signup",
        json={"username": "valid_user", "password": "p" * 129},
    )
    assert resp.status_code == 422

    # UserLogin schema validation rejects password > 128 characters
    with pytest.raises(ValidationError):
        schemas.UserLogin(username="valid_user", password="p" * 129)

    # UserCreate schema validation rejects password > 128 characters
    with pytest.raises(ValidationError):
        schemas.UserCreate(username="valid_user", password="p" * 129)

    # ChangePasswordIn schema validation rejects current_password or new_password > 128 characters
    with pytest.raises(ValidationError):
        schemas.ChangePasswordIn(current_password="p" * 129, new_password="validpassword123")
    with pytest.raises(ValidationError):
        schemas.ChangePasswordIn(current_password="validpassword123", new_password="p" * 129)

    # Langchain query param user_question exceeding 500 characters returns 422
    signup = client.post("/api/auth/signup", json={"username": "query_tester", "password": "password123"})
    token = signup.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    overlong_q = "q" * 501
    resp_q = client.get(f"/api/stock/AAPL/langchain-analysis?user_question={overlong_q}", headers=headers)
    assert resp_q.status_code == 422


def test_secret_key_validation():
    # Empty SECRET_KEY should raise ValidationError
    with pytest.raises(ValidationError):
        Settings(SECRET_KEY="")

    # Too short (< 16 chars) SECRET_KEY should raise ValidationError
    with pytest.raises(ValidationError):
        Settings(SECRET_KEY="short_key_123")

    # Insecure default SECRET_KEY should raise ValidationError
    with pytest.raises(ValidationError):
        Settings(SECRET_KEY="super_secret_key_for_stocksense")

    # Valid secret key initializes properly
    valid_settings = Settings(SECRET_KEY="a_secure_random_key_of_sufficient_length_32chars")
    assert valid_settings.SECRET_KEY == "a_secure_random_key_of_sufficient_length_32chars"


def test_preferences_crud_and_validation(client):
    # Register user
    signup_resp = client.post("/api/auth/signup", json={"username": "pref_user", "password": "password12345"})
    assert signup_resp.status_code == 200
    token = signup_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Update preferences with full valid payload
    valid_payload = {
        "risk_level": "High",
        "investment_type": "Short-term",
        "focus_type": "Sentiment",
        "budget_range": "$25,000",
        "expected_return": "18%",
    }
    put_resp = client.put("/api/preferences", json=valid_payload, headers=headers)
    assert put_resp.status_code == 200, put_resp.text
    put_data = put_resp.json()
    assert put_data["risk_level"] == "High"
    assert put_data["investment_type"] == "Short-term"
    assert put_data["focus_type"] == "Sentiment"
    assert put_data["budget_range"] == "$25,000"
    assert put_data["expected_return"] == "18%"

    # 2. Verify persistence via GET /api/preferences
    get_resp = client.get("/api/preferences", headers=headers)
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert get_data["risk_level"] == "High"
    assert get_data["investment_type"] == "Short-term"
    assert get_data["focus_type"] == "Sentiment"
    assert get_data["budget_range"] == "$25,000"
    assert get_data["expected_return"] == "18%"

    # 3. Reject wrong field names with 422 (extra="forbid")
    bad_field_resp1 = client.put("/api/preferences", json={"risk_tolerance": "High"}, headers=headers)
    assert bad_field_resp1.status_code == 422

    bad_field_resp2 = client.put("/api/preferences", json={"focus_area": "Technical"}, headers=headers)
    assert bad_field_resp2.status_code == 422

    bad_field_resp3 = client.put("/api/preferences", json={"investment_horizon": "Long-term"}, headers=headers)
    assert bad_field_resp3.status_code == 422

    # 4. Reject invalid literal values with 422
    assert client.put("/api/preferences", json={"risk_level": "UltraRisky"}, headers=headers).status_code == 422
    assert client.put("/api/preferences", json={"investment_type": "10-years"}, headers=headers).status_code == 422
    assert client.put("/api/preferences", json={"focus_type": "MomentumOnly"}, headers=headers).status_code == 422

    # 5. Partial update updates only supplied fields (model_dump(exclude_unset=True))
    partial_resp = client.put("/api/preferences", json={"expected_return": "35%"}, headers=headers)
    assert partial_resp.status_code == 200
    after_partial = client.get("/api/preferences", headers=headers).json()
    assert after_partial["expected_return"] == "35%"
    assert after_partial["risk_level"] == "High"
    assert after_partial["investment_type"] == "Short-term"
    assert after_partial["focus_type"] == "Sentiment"
    assert after_partial["budget_range"] == "$25,000"
