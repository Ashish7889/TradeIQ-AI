from fastapi.testclient import TestClient
from main import app
from database import engine, Base
import json

# Ensure DB is created
Base.metadata.create_all(bind=engine)

client = TestClient(app)

def run_tests():
    print("1. Testing Registration")
    signup_res = client.post("/api/auth/signup", json={"username": "testuser_fintech", "password": "password123"})
    
    if signup_res.status_code == 400 and "already registered" in signup_res.text:
       print("User already exists, proceeding to login...")
       
    print("2. Testing Login")
    login_res = client.post("/api/auth/login", data={"username": "testuser_fintech", "password": "password123"})
    assert login_res.status_code == 200, f"Login failed: {login_res.text}"
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("Login successful, token acquired.")
    
    print("3. Testing Preferences")
    prefs_res = client.put("/api/preferences", json={
        "risk_level": "Medium",
        "investment_type": "Long-term",
        "focus_type": "Technical",
        "budget_range": "$10k-$50k",
        "expected_return": "15%"
    }, headers=headers)
    assert prefs_res.status_code == 200, f"Prefs failed: {prefs_res.text}"
    print("Preferences saved:", prefs_res.json())
    
    print("4. Testing Watchlist")
    client.post("/api/watchlist/add", json={"ticker": "AAPL"}, headers=headers)
    client.post("/api/watchlist/add", json={"ticker": "MSFT"}, headers=headers)
    watch_res = client.get("/api/watchlist", headers=headers)
    assert watch_res.status_code == 200, f"Watchlist failed: {watch_res.text}"
    print("Watchlist:", watch_res.json())
    
    print("5. Testing AI Report Generation (Calling Groq API)")
    report_res = client.post("/api/report/generate", headers=headers)
    assert report_res.status_code == 200, f"Report failed: {report_res.text}"
    
    report_data = report_res.json()
    print("\n--- AI REPORT GENERATED ---\n")
    print(report_data.get("report", "No report string found"))
    print("\n---------------------------\n")
    print("All tests passed successfully.")

if __name__ == "__main__":
    run_tests()
