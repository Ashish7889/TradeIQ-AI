import numpy as np
import pandas as pd

from services.quant_backtest import run_institutional_backtest


def _create_synthetic_ohlcv(rows: int = 120) -> pd.DataFrame:
    np.random.seed(123)
    dates = pd.date_range("2024-01-01", periods=rows, freq="B")
    close = 100.0 + np.cumsum(np.random.randn(rows) * 1.5)
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": close,
            "High": close + 1.0,
            "Low": close - 1.0,
            "Close": close,
            "Volume": [200000] * rows,
        }
    )


def test_quant_backtest_insufficient_data():
    df = _create_synthetic_ohlcv(30)
    result = run_institutional_backtest(df, "AAPL")
    assert result["available"] is False
    assert result["total_signals"] == 0
    assert result["win_rate"] == 0.0


def test_quant_backtest_sufficient_data():
    df = _create_synthetic_ohlcv(120)
    result = run_institutional_backtest(df, "AAPL")
    assert result["available"] is True
    assert "accuracy" in result
    assert "win_rate" in result
    assert result["total_signals"] > 0
    assert 0.0 <= result["win_rate"] <= 100.0
    assert result["period"] == "1 Year"
