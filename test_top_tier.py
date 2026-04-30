import requests
import json

# Replace with your actual credentials or token if needed
# Since this is local dev, I'll assume I can hit the endpoint if the server is running.
# However, I should probably check the logs of the running main.py.

def test_top_tier_pipeline(ticker="TSLA"):
    url = f"http://127.0.0.1:8000/api/stock/{ticker}/langchain-analysis"
    
    # We need a token because it's Depends(get_current_user)
    # I'll try to find a user or create one.
    # For now, let's just check the code one last time.
    print(f"Testing pipeline for {ticker}...")

if __name__ == "__main__":
    test_top_tier_pipeline()
