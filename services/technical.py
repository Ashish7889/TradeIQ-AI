import pandas as pd
import pandas_ta 
import numpy as np

def calculate_technical_indicators(df: pd.DataFrame):
    """
    Given a pandas DataFrame with OHLCV data, calculates:
    SMA 20, SMA 50, SMA 200, RSI, MACD, Bollinger Bands, and Volatility.
    """
    if df is None or len(df) < 20: # Need at least 20 periods for SMA20 and BB
        return df 
    
    # We will copy to prevent SettingWithCopyWarning
    df = df.copy()
    
    # Ensure column names are standard
    required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
    if not all(col in df.columns for col in required_cols):
        return None
        
    # Calculate SMAs
    df.ta.sma(length=20, append=True)
    df.ta.sma(length=50, append=True)
    df.ta.sma(length=200, append=True)
    
    # RSI
    df.ta.rsi(length=14, append=True)
    
    # MACD
    df.ta.macd(fast=12, slow=26, signal=9, append=True)
    
    # Bollinger Bands
    df.ta.bbands(length=20, std=2, append=True)
    
    # Volatility (standard deviation of daily returns over 20 days)
    df['Returns'] = df['Close'].pct_change()
    df['Volatility'] = df['Returns'].rolling(window=20).std() * np.sqrt(252) * 100 # Annualized percentage
    
    return df

def generate_technical_summary(df: pd.DataFrame) -> dict:
    if df is None or df.empty:
        return {"tech_score": 50, "numerical_evidence": ["Insufficient data for technical analysis."]}
        
    latest = df.iloc[-1]
    
    # Extract values safely
    close = latest.get('Close', 0)
    sma20 = latest.get('SMA_20', 0)
    sma50 = latest.get('SMA_50', 0)
    sma200 = latest.get('SMA_200', 0)
    rsi = latest.get('RSI_14', 50)
    macd = latest.get('MACD_12_26_9', 0)
    macdh = latest.get('MACDh_12_26_9', 0) # MACD Histogram
    volatility = latest.get('Volatility', 0)
    
    evidence = []
    score = 50 # Start neutral
    
    # ── Trend Analysis (SMA Proximity) ─────────────────
    if not pd.isna(sma20) and not pd.isna(sma50) and not pd.isna(sma200):
        # Bullish trend: close > 20 > 50 > 200
        if close > sma20:
            score += 10
            diff = ((close - sma20) / sma20) * 100
            evidence.append(f"Price is trading {diff:.1f}% above 20-day SMA.")
        else:
            score -= 10
            diff = ((sma20 - close) / sma20) * 100
            evidence.append(f"Price is trading {diff:.1f}% below 20-day SMA.")
            
        if close > sma200:
            score += 10
            diff = ((close - sma200) / sma200) * 100
            evidence.append(f"Price matches long-term bullish trend (Above 200-day SMA by {diff:.1f}%).")
        else:
            score -= 15
            diff = ((sma200 - close) / sma200) * 100
            evidence.append(f"Price matches long-term bearish trend (Below 200-day SMA by {diff:.1f}%).")

    # ── RSI (Momentum) ──────────────────────────────
    if not pd.isna(rsi):
        evidence.append(f"RSI (14) is at {rsi:.1f}.")
        if rsi < 30: # Oversold (Buy signal)
            score += 20
            evidence.append("RSI indicates heavily oversold conditions (Potential Rebound).")
        elif rsi > 70: # Overbought (Sell signal)
            score -= 15
            evidence.append("RSI indicates overbought conditions (Potential Pullback).")
        elif 40 <= rsi <= 60:
            score += 5 # Solid neutral/sideways momentum
            
    # ── MACD (Momentum) ─────────────────────────────
    if not pd.isna(macdh):
        if macdh > 0:
            score += 10
            evidence.append("MACD Histogram is positive (Bullish Momentum).")
        else:
            score -= 10
            evidence.append("MACD Histogram is negative (Bearish Momentum).")

    # Bounds check
    score = max(0, min(100, score))
    
    return {
        "tech_score": score,
        "numerical_evidence": evidence,
        "rsi": float(rsi) if not pd.isna(rsi) else None,
        "macd": float(macd) if not pd.isna(macd) else None,
        "sma20": float(sma20) if not pd.isna(sma20) else None,
        "sma50": float(sma50) if not pd.isna(sma50) else None,
        "sma200": float(sma200) if not pd.isna(sma200) else None,
        "volatility": float(volatility) if not pd.isna(volatility) else None,
        "interpretations": {
            "trend": "Bullish" if score > 60 else "Bearish" if score < 40 else "Neutral",
            "rsi": "Overbought" if rsi > 70 else "Oversold" if rsi < 30 else "Neutral"
        }
    }
