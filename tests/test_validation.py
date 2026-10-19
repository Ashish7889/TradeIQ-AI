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
