from unittest.mock import patch

import numpy as np
import pandas as pd

from services.risk_assessment import calculate_risk_metrics


def _create_synthetic_ohlcv(rows: int = 100) -> pd.DataFrame:
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", periods=rows, freq="B")
    close = 100.0 + np.cumsum(np.random.randn(rows))
    return pd.DataFrame(
        {
            "Date": dates,
            "Open": close,
            "High": close + 1.0,
            "Low": close - 1.0,
            "Close": close,
            "Volume": [100000] * rows,
        }
    )


@patch("services.risk_assessment._fetch_benchmark")
def test_calculate_risk_metrics_success(mock_benchmark):
    rows = 100
    dates = pd.date_range("2024-01-01", periods=rows, freq="B")
    mock_benchmark.return_value = pd.Series(
        np.random.normal(0.0005, 0.01, size=rows),
        index=dates,
    )

    df = _create_synthetic_ohlcv(rows)
    metrics = calculate_risk_metrics(df)

    assert "annualized_volatility_pct" in metrics
    assert "var_95_daily_pct" in metrics
    assert "sharpe_ratio" in metrics
    assert "max_drawdown_pct" in metrics
    assert "risk_grade" in metrics
    assert isinstance(metrics["max_drawdown_pct"], float)
    assert metrics["max_drawdown_pct"] <= 0.0


def test_calculate_risk_metrics_insufficient_data():
    df = _create_synthetic_ohlcv(15)
    metrics = calculate_risk_metrics(df)
    assert metrics["risk_grade"] == "N/A"
    assert metrics["annualized_volatility_pct"] is None
