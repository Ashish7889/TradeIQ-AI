import numpy as np
import pandas as pd

from services.technical import (
    calculate_technical_indicators,
    generate_technical_summary,
)


def _create_synthetic_ohlcv(rows: int = 100) -> pd.DataFrame:
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=rows, freq="B")
    close = 100.0 + np.cumsum(np.random.randn(rows))
    high = close + np.random.rand(rows) * 2
    low = close - np.random.rand(rows) * 2
    open_p = close + np.random.randn(rows) * 0.5
    volume = np.random.randint(100000, 1000000, size=rows)
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": open_p,
            "High": high,
            "Low": low,
            "Close": close,
            "Volume": volume,
        }
    )


def test_calculate_technical_indicators_success():
    df = _create_synthetic_ohlcv(100)
    result = calculate_technical_indicators(df)
    assert result is not None
    assert "SMA_20" in result.columns
    assert "SMA_50" in result.columns
    assert "RSI_14" in result.columns
    assert "MACD_12_26_9" in result.columns
    assert "Volatility" in result.columns


def test_calculate_technical_indicators_insufficient_data():
    df = _create_synthetic_ohlcv(10)
    result = calculate_technical_indicators(df)
    # len < 20 returns original df without calculations
    assert "SMA_20" not in result.columns


def test_calculate_technical_indicators_missing_columns():
    df = pd.DataFrame({"Close": [10.0] * 30})
    result = calculate_technical_indicators(df)
    assert result is None


def test_generate_technical_summary_success():
    df = _create_synthetic_ohlcv(100)
    calc_df = calculate_technical_indicators(df)
    summary = generate_technical_summary(calc_df)
    assert summary["available"] is True
    assert summary["tech_score"] is not None
    assert isinstance(summary["numerical_evidence"], list)
    assert "rsi" in summary
    assert "macd" in summary


def test_generate_technical_summary_empty():
    summary = generate_technical_summary(pd.DataFrame())
    assert summary["available"] is False
    assert summary["tech_score"] is None
