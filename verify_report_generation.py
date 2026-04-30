import requests
import json
import time

BASE_URL = "http://localhost:8000/api"
TEST_USER = f"test_user_{int(time.time())}"
TEST_PASS = "test_pass_123"

def verify():
    print(f"--- 🚀 Starting verification for {TEST_USER} ---")
    
    # 1. Signup
    print("\n1. Signing up...")
    res = requests.post(f"{BASE_URL}/auth/signup", json={"username": TEST_USER, "password": TEST_PASS})
    if res.status_code != 200:
        print(f"FAILED: {res.text}")
        return
    token = res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    print("SUCCESS")

    # 2. Add to Watchlist
    print("\n2. Adding stocks to watchlist...")
    for ticker in ["AAPL", "TSLA"]:
        res = requests.post(f"{BASE_URL}/watchlist/add", headers=headers, json={"ticker": ticker})
        print(f"   - {ticker}: {res.json().get('message')}")

    # 3. Generate Report
    print("\n3. Generating AI Report (Parallel Pipeline)...")
    start = time.time()
    res = requests.post(f"{BASE_URL}/report/generate", headers=headers)
    elapsed = time.time() - start
    
    if res.status_code != 200:
        print(f"FAILED (Status: {res.status_code}): {res.text}")
        return
    
    report = res.json().get("report")
    print(f"\n✅ SUCCESS (Time: {elapsed:.2f}s)")
    print("\n--- REPORT PREVIEW ---")
    print(report[:800] + "...")
    print("\n--- REPORT VERIFIED ---")
    
    with open("verify_result_report.md", "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\nFull report saved to 'verify_result_report.md'")

if __name__ == "__main__":
    verify()
