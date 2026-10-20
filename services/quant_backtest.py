import logging

import pandas as pd

from services.technical import calculate_technical_indicators

logger = logging.getLogger(__name__)


def run_institutional_backtest(df: pd.DataFrame, ticker: str) -> dict:
    """
    Simulates the quantitative strategy over the last 1 year.

    1. Generates signals based on RSI and SMA crossovers.
    2. Measures price movement 10 days after each signal.
    3. Calculates the Accuracy (Hit Rate).
    """
    try:
        if df is None or len(df) < 50:
            return {"available": False, "accuracy": 0.0, "total_signals": 0, "win_rate": 0.0}

        data = calculate_technical_indicators(df.copy())

        # Simple Signal logic for backtesting (RSI + SMA)
        # 1 = BUY, -1 = SELL, 0 = HOLD
        data["signal"] = 0

        # BUY: RSI < 35 or Price crosses above SMA50
        data.loc[(data["RSI_14"] < 35) | (data["Close"] > data["SMA_50"]), "signal"] = 1
        # SELL: RSI > 65 or Price crosses below SMA50
        data.loc[(data["RSI_14"] > 65) | (data["Close"] < data["SMA_50"]), "signal"] = -1

        # Forward Return (10-day window)
        data["forward_return"] = data["Close"].shift(-10) / data["Close"] - 1

        # Distinct trade entries: trigger only when signal transitions (new trade initiation)
        data["prev_signal"] = data["signal"].shift(1).fillna(0)
        trades = data[
            (data["signal"] != 0) & (data["signal"] != data["prev_signal"]) & (data["forward_return"].notna())
        ].copy()

        if len(trades) == 0:
            return {"available": False, "accuracy": 0.0, "total_signals": 0, "win_rate": 0.0}

        trades["is_correct"] = False
        trades.loc[(trades["signal"] == 1) & (trades["forward_return"] > 0), "is_correct"] = True
        trades.loc[(trades["signal"] == -1) & (trades["forward_return"] < 0), "is_correct"] = True

        accuracy = float((trades["is_correct"].sum() / len(trades)) * 100)
        win_rate = round(accuracy, 1)

        logger.info(f"[Backtest] {ticker} Accuracy: {win_rate}% over {len(trades)} distinct trades.")

        return {
            "available": True,
            "accuracy": win_rate,
            "win_rate": win_rate,
            "total_signals": len(trades),
            "period": "1 Year",
        }
    except Exception as e:
        logger.error(f"Backtest failed for {ticker}: {e}")
        return {"available": False, "accuracy": 0.0, "total_signals": 0, "win_rate": 0.0}
