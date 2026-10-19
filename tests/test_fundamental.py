from unittest.mock import MagicMock, patch

from services.fundamental import evaluate_fundamentals


@patch("yfinance.Ticker")
def test_evaluate_fundamentals_success(mock_ticker):
    mock_instance = MagicMock()
    mock_instance.info = {
        "trailingPE": 15.5,
        "trailingEps": 4.20,
        "revenueGrowth": 0.20,
        "profitMargins": 0.25,
        "debtToEquity": 45.0,
    }
    mock_ticker.return_value = mock_instance

    result = evaluate_fundamentals("AAPL")
    assert result["available"] is True
    assert result["fundamental_score"] is not None
    assert result["fundamental_score"] > 50
    assert result["metrics"]["pe_ratio"] == 15.5
    assert len(result["numerical_evidence"]) > 0


@patch("yfinance.Ticker")
def test_evaluate_fundamentals_unprofitable(mock_ticker):
    mock_instance = MagicMock()
    mock_instance.info = {
        "trailingPE": 45.0,
        "trailingEps": -1.5,
        "revenueGrowth": -0.05,
        "profitMargins": -0.10,
        "debtToEquity": 180.0,
    }
    mock_ticker.return_value = mock_instance

    result = evaluate_fundamentals("RISK")
    assert result["available"] is True
    assert result["fundamental_score"] < 50


@patch("yfinance.Ticker")
def test_evaluate_fundamentals_missing_data(mock_ticker):
    mock_instance = MagicMock()
    mock_instance.info = {}
    mock_ticker.return_value = mock_instance

    result = evaluate_fundamentals("EMPTY")
    assert result["available"] is False
    assert result["fundamental_score"] is None


@patch("yfinance.Ticker")
def test_evaluate_fundamentals_exception(mock_ticker):
    mock_ticker.side_effect = RuntimeError("Network error")

    result = evaluate_fundamentals("ERR")
    assert result["available"] is False
    assert result["fundamental_score"] is None
