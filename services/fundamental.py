import yfinance as yf
import logging

logger = logging.getLogger(__name__)

def evaluate_fundamentals(ticker: str):
    ticker = ticker.upper()
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        if not info:
             return {"fundamental_score": 50, "numerical_evidence": ["Fundamental data unavailable."]}
             
        # Extract metrics
        pe_ratio = info.get('trailingPE') or info.get('forwardPE', 0)
        eps = info.get('trailingEps', 0)
        revenue_growth = info.get('revenueGrowth', 0)
        profit_margins = info.get('profitMargins', 0)
        debt_to_equity = info.get('debtToEquity', 0)
        
        evidence = []
        score = 50 # Base score
        
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
            if eps > 0: score += 10
            else: 
                score -= 15
                evidence.append("Company is currently reporting negative earnings (diluted EPS).")

        # ── Revenue Growth ──────────────────────────
        if revenue_growth:
            growth_pct = revenue_growth * 100
            evidence.append(f"Revenue Growth is {growth_pct:.1f}%.")
            if revenue_growth > 0.15: score += 15
            elif revenue_growth < 0: 
                score -= 10
                evidence.append("Revenue is shrinking year-over-year.")

        # ── profit Margins ──────────────────────────
        if profit_margins:
            margin_pct = profit_margins * 100
            evidence.append(f"Profit Margin is {margin_pct:.1f}%.")
            if profit_margins > 0.20: score += 10
            elif profit_margins < 0.05: score -= 5

        # ── Debt to Equity ──────────────────────────
        if debt_to_equity:
            evidence.append(f"Debt-to-Equity Ratio is {debt_to_equity:.2f}.")
            if debt_to_equity < 50: score += 5
            elif debt_to_equity > 150: 
                score -= 10
                evidence.append("High leverage detected (D/E > 1.5).")

        # Bounds check
        score = max(0, min(100, score))
        
        return {
            "fundamental_score": score,
            "numerical_evidence": evidence,
            "metrics": {
                "pe_ratio": round(pe_ratio, 2) if pe_ratio else None,
                "eps": round(eps, 2) if eps else None,
                "revenue_growth": round(revenue_growth, 4) if revenue_growth else None,
                "profit_margins": round(profit_margins, 4) if profit_margins else None,
                "debt_to_equity": round(debt_to_equity, 2) if debt_to_equity else None
            }
        }
        
    except Exception as e:
        logger.error(f"Error fetching fundamentals for {ticker}: {e}")
        return {"fundamental_score": 50, "numerical_evidence": [f"Error: {str(e)}"]}
