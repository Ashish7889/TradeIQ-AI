import logging
import time
from typing import Any

import yfinance as yf

logger = logging.getLogger(__name__)

# In-memory TTL cache for fundamentals: {ticker: (cached_at_epoch, data)}
_FUNDAMENTALS_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
CACHE_TTL_SECONDS = 1800.0  # 30 minutes


def clear_fundamentals_cache() -> None:
    """Clears the fundamentals in-memory cache (useful for testing)."""
    _FUNDAMENTALS_CACHE.clear()


def evaluate_fundamentals(ticker: str) -> dict[str, Any]:
    ticker = ticker.upper()
    now = time.time()

    # 1. Check TTL Cache
    if ticker in _FUNDAMENTALS_CACHE:
        cached_time, cached_data = _FUNDAMENTALS_CACHE[ticker]
        if now - cached_time < CACHE_TTL_SECONDS:
            logger.debug(f"[Fundamentals] Cache hit for {ticker}")
            return cached_data

    # 2. Fetch with Retry / Exponential Backoff
    info = None
    max_retries = 3
    for attempt in range(max_retries):
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            if info:
                break
        except Exception as err:
            logger.warning(f"[Fundamentals] Attempt {attempt + 1}/{max_retries} failed for {ticker}: {err}")
            if attempt < max_retries - 1:
                time.sleep(0.3 * (2**attempt))

    if not info:
        result = {
            "available": False,
            "fundamental_score": None,
            "numerical_evidence": ["Fundamental data unavailable (provider rate-limited or missing)."],
            "metrics": None,
        }
        # Cache negative result for shorter duration (5 mins) to prevent spamming
        _FUNDAMENTALS_CACHE[ticker] = (now - CACHE_TTL_SECONDS + 300.0, result)
        return result

    try:
        # Extract metrics
        pe_ratio = info.get("trailingPE") or info.get("forwardPE", 0)
        eps = info.get("trailingEps", 0)
        revenue_growth = info.get("revenueGrowth", 0)
        profit_margins = info.get("profitMargins", 0)
        debt_to_equity = info.get("debtToEquity", 0)

        evidence = []
        score = 50  # Base score

        # ── PE Ratio ────────────────────────────────
        if pe_ratio:
            evidence.append(f"P/E Ratio is {pe_ratio:.2f}.")
            if pe_ratio < 20:
                score += 10
            elif pe_ratio > 35:
                score -= 10
                evidence.append("P/E Ratio is high compared to historical sector averages.")

        # ── EPS ─────────────────────────────────────
        if eps:
            evidence.append(f"Trailing EPS is ${eps:.2f}.")
            if eps > 0:
                score += 10
            else:
                score -= 15
                evidence.append("Company is currently reporting negative earnings (diluted EPS).")

        # ── Revenue Growth ──────────────────────────
        if revenue_growth:
            growth_pct = revenue_growth * 100
            evidence.append(f"Revenue Growth is {growth_pct:.1f}%.")
            if revenue_growth > 0.15:
                score += 15
            elif revenue_growth < 0:
                score -= 10
                evidence.append("Revenue is shrinking year-over-year.")

        # ── Profit Margins ──────────────────────────
        if profit_margins:
            margin_pct = profit_margins * 100
            evidence.append(f"Profit Margin is {margin_pct:.1f}%.")
            if profit_margins > 0.20:
                score += 10
            elif profit_margins < 0.05:
                score -= 5

        # ── Debt to Equity ──────────────────────────
        if debt_to_equity:
            evidence.append(f"Debt-to-Equity Ratio is {debt_to_equity:.2f}.")
            if debt_to_equity < 50:
                score += 5
            elif debt_to_equity > 150:
                score -= 10
                evidence.append("High leverage detected (D/E > 1.5).")

        # Bounds check
        score = max(0, min(100, score))

        result = {
            "available": True,
            "fundamental_score": score,
            "numerical_evidence": evidence,
            "metrics": {
                "pe_ratio": round(pe_ratio, 2) if pe_ratio else None,
                "eps": round(eps, 2) if eps else None,
                "revenue_growth": round(revenue_growth, 4) if revenue_growth else None,
                "profit_margins": round(profit_margins, 4) if profit_margins else None,
                "debt_to_equity": round(debt_to_equity, 2) if debt_to_equity else None,
            },
        }
        _FUNDAMENTALS_CACHE[ticker] = (now, result)
        return result

    except Exception as e:
        logger.error(f"Error parsing fundamentals for {ticker}: {e}")
        result = {
            "available": False,
            "fundamental_score": None,
            "numerical_evidence": [f"Error: {e!s}"],
            "metrics": None,
        }
        _FUNDAMENTALS_CACHE[ticker] = (now - CACHE_TTL_SECONDS + 300.0, result)
        return result
