"""
StockSense AI — Risk Assessment Service
========================================
Algorithmic risk quantification engine. No LLM involved — all calculations
are deterministic mathematical/statistical methods used in institutional finance.

Metrics:
  - Annualized Volatility (annualized std dev of daily log returns)
  - Value at Risk @ 95% confidence (historical simulation method)
  - Beta vs S&P 500 (SPY as benchmark)
  - Sharpe Ratio (risk-adjusted return)
  - Maximum Drawdown (peak-to-trough loss)
  - Calmar Ratio (return / max drawdown)
"""

import logging
import numpy as np
import pandas as pd
import yfinance as yf
from scipy import stats

logger = logging.getLogger(__name__)


def _fetch_benchmark(period: str = "1y") -> pd.Series:
    """Fetches SPY (S&P 500 ETF) daily returns as the market benchmark."""
    try:
        spy = yf.Ticker("SPY")
        df = spy.history(period=period)
        if df.empty:
            return None
        return df["Close"].pct_change().dropna()
    except Exception as e:
        logger.error(f"Failed to fetch SPY benchmark: {e}")
        return None


def calculate_risk_metrics(df: pd.DataFrame, risk_free_rate: float = 0.05) -> dict:
    """
    Primary risk assessment function. Takes OHLCV DataFrame and returns
    a full institutional-grade risk profile.

    Args:
        df: OHLCV DataFrame from fetch_stock_data()
        risk_free_rate: Annual risk-free rate (default 5% = current US T-bill approx)

    Returns:
        dict with annualized_volatility, var_95, beta, sharpe_ratio,
        max_drawdown, calmar_ratio, risk_grade, risk_summary
    """
    if df is None or len(df) < 30:
        return _empty_risk_metrics()

    try:
        close = df["Close"].copy()

        # ── 1. Daily Log Returns ──────────────────────────────────────────────
        # Log returns are preferred over simple returns in risk calculations
        # because they are symmetrically distributed and time-additive.
        log_returns = np.log(close / close.shift(1)).dropna()

        # ── 2. Annualized Volatility ──────────────────────────────────────────
        # σ_annual = σ_daily × √252  (252 trading days per year)
        daily_vol = log_returns.std()
        annualized_vol = daily_vol * np.sqrt(252) * 100  # express as %
        annualized_vol = round(float(annualized_vol), 2)

        # ── 3. Value at Risk @ 95% (Historical Simulation) ───────────────────
        # VaR answers: "What is the maximum loss at the 95th percentile?"
        # We use the 5th percentile of the actual return distribution.
        var_95_daily = float(np.percentile(log_returns, 5))
        var_95_annual = var_95_daily * np.sqrt(252) * 100  # annualized %
        var_95 = round(var_95_daily * 100, 2)  # report as daily %
        var_95_annual = round(var_95_annual, 2)

        # ── 4. Beta vs S&P 500 ────────────────────────────────────────────────
        # β > 1: stock is more volatile than the market
        # β < 1: stock is less volatile (defensive)
        # β < 0: stock moves inversely to the market
        beta = None
        benchmark_returns = _fetch_benchmark()
        if benchmark_returns is not None:
            # Align both series on the same dates
            stock_aligned = log_returns.copy()
            stock_aligned.index = pd.to_datetime(stock_aligned.index).normalize()
            bench_aligned = benchmark_returns.copy()
            bench_aligned.index = pd.to_datetime(bench_aligned.index).normalize()

            combined = pd.DataFrame({
                "stock": stock_aligned,
                "bench": bench_aligned
            }).dropna()

            if len(combined) > 20:
                slope, _, _, _, _ = stats.linregress(combined["bench"], combined["stock"])
                beta = round(float(slope), 3)

        # ── 5. Sharpe Ratio ───────────────────────────────────────────────────
        # Sharpe = (Annual Return - Risk Free Rate) / Annual Volatility
        # Measures how much return you get per unit of risk.
        # > 1.0 = Good, > 2.0 = Excellent, < 0 = Underperforming risk-free assets
        annual_return = float(log_returns.mean()) * 252  # annualized mean return
        daily_rf = risk_free_rate / 252
        excess_daily_returns = log_returns - daily_rf
        sharpe = float(excess_daily_returns.mean() / excess_daily_returns.std()) * np.sqrt(252)
        sharpe = round(sharpe, 3)

        # ── 6. Maximum Drawdown ───────────────────────────────────────────────
        # The largest peak-to-trough percentage decline in the price series.
        # Critical metric for understanding downside risk in real scenarios.
        cumulative = (1 + log_returns).cumprod()
        rolling_max = cumulative.cummax()
        drawdown = (cumulative - rolling_max) / rolling_max
        max_drawdown = round(float(drawdown.min()) * 100, 2)  # negative %

        # ── 7. Calmar Ratio ───────────────────────────────────────────────────
        # Calmar = Annual Return / |Max Drawdown|
        # Measures recovery: how much return per unit of worst-case drawdown
        if max_drawdown != 0:
            calmar = round(annual_return / abs(max_drawdown / 100), 3)
        else:
            calmar = None

        # ── 8. Risk Grading ───────────────────────────────────────────────────
        risk_grade, risk_summary, risk_score, evidence = _grade_risk(
            annualized_vol, var_95, beta, sharpe, max_drawdown
        )

        return {
            "risk_score": risk_score,
            "numerical_evidence": evidence,
            "annualized_volatility_pct": annualized_vol,
            "var_95_daily_pct": var_95,
            "var_95_annual_pct": var_95_annual,
            "beta_vs_spy": beta,
            "sharpe_ratio": sharpe,
            "max_drawdown_pct": max_drawdown,
            "calmar_ratio": calmar,
            "annual_return_pct": round(annual_return * 100, 2),
            "risk_grade": risk_grade,
            "risk_summary": risk_summary,
        }

    except Exception as e:
        logger.error(f"Risk assessment calculation failed: {e}")
        return _empty_risk_metrics()


def _grade_risk(vol: float, var_95: float, beta: float, sharpe: float, drawdown: float) -> tuple:
    """
    Assigns an institutional risk grade (A–F) and a numeric risk_score (0-100).
    Higher score = Lower risk.
    """
    total_score = 0  # Higher = lower risk (Conservative)
    evidence = []

    # ── Volatility (30 pts) ──────────────────────────
    evidence.append(f"Annualized Volatility is {vol}%.")
    if vol < 15: total_score += 30
    elif vol < 25: total_score += 20
    elif vol < 40: 
        total_score += 10
        evidence.append("Volatility is elevated (Higher than S&P 500 average of ~16%).")
    else:
        evidence.append("Extreme volatility detected (>40% annualized).")

    # ── Sharpe Ratio (30 pts) ────────────────────────
    evidence.append(f"Sharpe Ratio (Risk-Adjusted Return) is {sharpe}.")
    if sharpe > 1.5: total_score += 30
    elif sharpe > 0.5: total_score += 15
    elif sharpe < 0: 
        evidence.append("Negative Sharpe Ratio: Returns do not justify the risk taken.")

    # ── Max Drawdown (20 pts) ────────────────────────
    evidence.append(f"Maximum Drawdown is {drawdown}%.")
    if drawdown > -15: total_score += 20
    elif drawdown > -30: total_score += 10
    else:
        evidence.append("Significant downside exposure (Drawdown > 30%).")

    # ── Beta (20 pts) ────────────────────────────────
    if beta is not None:
        evidence.append(f"Beta vs S&P 500 is {beta}.")
        if 0.5 <= beta <= 1.3: total_score += 20
        elif beta > 1.5: 
            evidence.append(f"High sensitivity: Stock is {beta}x as volatile as the market.")
        elif beta < 0.3:
            evidence.append("Low correlation: Defensive or non-market correlated asset.")

    # Map score to grade
    if total_score >= 80: grade = "A"
    elif total_score >= 60: grade = "B"
    elif total_score >= 40: grade = "C"
    elif total_score >= 20: grade = "D"
    else: grade = "F"

    summary = f"Risk Score: {total_score}/100. Grade: {grade}. "
    if grade in ["A", "B"]: summary += "Suitable for conservative/institutional risk profiles."
    else: summary += "High-risk profile. Frequent monitoring required."

    return grade, summary, total_score, evidence


def _empty_risk_metrics() -> dict:
    return {
        "annualized_volatility_pct": None,
        "var_95_daily_pct": None,
        "var_95_annual_pct": None,
        "beta_vs_spy": None,
        "sharpe_ratio": None,
        "max_drawdown_pct": None,
        "calmar_ratio": None,
        "annual_return_pct": None,
        "risk_grade": "N/A",
        "risk_summary": "Insufficient data for risk assessment.",
    }
