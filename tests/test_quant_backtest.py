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


def test_quant_backtest_distinct_trades_counted():
    # In a 120-row dataframe, distinct trades should be significantly lower than total row count
    df = _create_synthetic_ohlcv(120)
    result = run_institutional_backtest(df, "AAPL")
    assert result["available"] is True
    assert result["total_signals"] < 120
    assert isinstance(result["total_signals"], int)


def test_quant_backtest_consecutive_signals_not_double_counted():
    # Construct data where price stays steadily above SMA50
    # Prior implementation would count every single day (>50 signals)
    # Distinct trade implementation must count only transitions (very few trades)
    df = _create_synthetic_ohlcv(80)
    # Force close prices to trend monotonically up after day 50 so SMA50 is consistently below close
    df.loc[50:, "Close"] = [100.0 + i * 2.0 for i in range(30)]
    result = run_institutional_backtest(df, "MSFT")
    assert result["available"] is True
    # The 30 trending days should result in at most a single trade entry, not 30 separate signals
    assert result["total_signals"] < 10
