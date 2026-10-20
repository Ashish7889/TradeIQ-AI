import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from dependencies import valid_ticker
from schemas import WatchlistAdd


@pytest.mark.parametrize("ticker", ["AAPL", "MSFT", "BRK.B", "BF-B", "A", "GOOGL"])
def test_valid_ticker_dependency(ticker):
    assert valid_ticker(ticker) == ticker


@pytest.mark.parametrize("ticker", ["aapl", "TOOLONGTICKER", "AAPL$", "GOOG!", "", "A B", "TSLA@"])
def test_invalid_ticker_dependency(ticker):
    with pytest.raises(HTTPException) as exc_info:
        valid_ticker(ticker)
    assert exc_info.value.status_code == 422


def test_watchlist_add_schema_validation():
    item = WatchlistAdd(ticker="NVDA")
    assert item.ticker == "NVDA"

    with pytest.raises(ValidationError):
        WatchlistAdd(ticker="invalid$$")


def test_health_and_root_endpoints():
    from fastapi.testclient import TestClient

    from main import app

    client = TestClient(app)

    # Root endpoint responds to GET and HEAD
    assert client.get("/").status_code == 200
    assert client.head("/").status_code == 200

    # Health endpoints respond to GET and HEAD with status ok
    for path in ["/health", "/healthz"]:
        get_res = client.get(path)
        assert get_res.status_code == 200
        assert get_res.json()["status"] == "ok"

        head_res = client.head(path)
        assert head_res.status_code == 200
