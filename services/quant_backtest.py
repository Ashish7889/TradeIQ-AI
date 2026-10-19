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
        data['signal'] = 0
        
        # BUY: RSI < 35 or Price crosses above SMA50
        data.loc[(data['RSI_14'] < 35) | (data['Close'] > data['SMA_50']), 'signal'] = 1
        # SELL: RSI > 65 or Price crosses below SMA50
        data.loc[(data['RSI_14'] > 65) | (data['Close'] < data['SMA_50']), 'signal'] = -1
        
        # Forward Return (10-day window)
        data['forward_return'] = data['Close'].shift(-10) / data['Close'] - 1
        
        # Evaluate Accuracy
        # Success if Signal was 1 and Return > 0, OR Signal was -1 and Return < 0
        signals = data[data['signal'] != 0].copy()
        
        if len(signals) == 0:
            return {"available": False, "accuracy": 0.0, "total_signals": 0, "win_rate": 0.0}

        signals['is_correct'] = False
        signals.loc[(signals['signal'] == 1) & (signals['forward_return'] > 0), 'is_correct'] = True
        signals.loc[(signals['signal'] == -1) & (signals['forward_return'] < 0), 'is_correct'] = True
        
        accuracy = float((signals['is_correct'].sum() / len(signals)) * 100)
        win_rate = round(accuracy, 1)
        
        logger.info(f"[Backtest] {ticker} Accuracy: {win_rate}% over {len(signals)} signals.")
        
        return {
            "available": True,
            "accuracy": win_rate,
            "win_rate": win_rate,
            "total_signals": len(signals),
            "period": "1 Year"
        }
    except Exception as e:
        logger.error(f"Backtest failed for {ticker}: {e}")
        return {"available": False, "accuracy": 0.0, "total_signals": 0, "win_rate": 0.0}
