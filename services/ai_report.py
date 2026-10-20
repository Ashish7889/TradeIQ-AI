"""
StockSense AI — AI Report Generation Service
=============================================
Upgraded to use LangChain LLMChain + ChatPromptTemplate + StrOutputParser.
Replaces direct google.generativeai SDK calls.

This service handles the /report/generate endpoint (watchlist-based report).
For the full sequential pipeline report, see langchain_agent.py.
"""

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

# ── LangChain ─────────────────────────────────────────────────────────────────
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field

# ── Project Services ─────────────────────────────────────────────────────────
from sqlalchemy.orm import Session

from app.config import settings
from models import User, UserPreference, Watchlist
from services.fundamental import evaluate_fundamentals
from services.quant_backtest import run_institutional_backtest
from services.sentiment import analyze_sentiment
from services.stock_data import fetch_stock_data
from services.technical import (
    calculate_technical_indicators,
    generate_technical_summary,
)

logger = logging.getLogger(__name__)
GROQ_API_KEY = settings.GROQ_API_KEY
PRIMARY_MODEL = settings.GROQ_MODEL
FALLBACK_MODEL = settings.GROQ_FALLBACK_MODEL


class ReportOutput(BaseModel):
    report: str = Field(description="The full Markdown report text with sections and highlights.")
    final_score: int = Field(description="Weighted final quant score (0-100).")
    score_breakdown: dict = Field(description="Breakdown: {technical, fundamental, sentiment, risk} (0-100 each).")
    recommendation: str = Field(description="BUY, HOLD, or SELL.")
    confidence_score: int = Field(description="0-100% confidence level.")
    strategy_accuracy: float = Field(description="1-year Backtested Strategy Accuracy (%).")
    decision_triggers: list = Field(description="Specific data triggers that would change this rating.")


def _build_report_chain(model: str = PRIMARY_MODEL):
    """Builds the Top-Tier Quant Report Chain returning structured JSON with temperature=0."""
    llm = ChatGroq(
        model=model,
        api_key=GROQ_API_KEY,
        temperature=0.0,
        model_kwargs={"response_format": {"type": "json_object"}},
    )

    parser = JsonOutputParser(pydantic_object=ReportOutput)

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                (
                    "You are QuantCore, an institutional-grade market reasoning engine and senior buy-side analyst. "
                    "You produce precise, evidence-anchored, professional investment research reports. "
                    "CRITICAL RULES:\n"
                    "1. Use only supplied market data — never invent metrics, prices, or events.\n"
                    "2. The quantitative scores, rating, and score breakdowns have ALREADY been computed deterministically "
                    "by the python quant engine based on the investor's tactical profile. You MUST use these exact computed values.\n"
                    "3. Your task is to write the executive narrative memorandum explaining and justifying these ratings based on the provided evidence.\n"
                    "4. If a metric is missing (e.g. fundamentals rate-limited), explain that valuation metrics were unavailable.\n"
                    "5. Output structured JSON only following the schema.\n\n"
                    "{format_instructions}"
                ),
            ),
            (
                "human",
                (
                    "Generate an executive personalized quant research report for the following investment profile.\n\n"
                    "=== INVESTOR PROFILE ===\n"
                    "Profile: {applied_profile}\n"
                    "Risk Level: {risk_level}\n"
                    "Investment Horizon: {investment_type}\n"
                    "Focus Area: {focus_type}\n"
                    "Portfolio Budget: {budget_range}\n"
                    "Target Annual Return: {expected_return}\n\n"
                    "=== DETERMINISTIC QUANT AUDIT & RATINGS ===\n"
                    "Analysis Weights Applied: {weights_info}\n"
                    "Rating Thresholds: {thresholds_info}\n"
                    "Calculated Portfolio Score: {computed_score}/100\n"
                    "Calculated Rating: {computed_recommendation}\n"
                    "Calculated Score Breakdown: {computed_breakdown}\n"
                    "Ticker Evaluations:\n{deterministic_results}\n\n"
                    "=== PORTFOLIO DATA ===\n"
                    "{stock_data}\n\n"
                    "=== REPORT STRUCTURE INSTRUCTIONS ===\n"
                    "1. Market Overview: 2-3 direct, data-backed sentences reflecting the {applied_profile} profile.\n"
                    "2. Stock Comparison Table: Markdown pipe table: Ticker | Score | Backtest win rate | Rec | Key Signal.\n"
                    "3. Allocation & Top Picks: Justify using raw numbers from data, aligning with target return {expected_return} and budget {budget_range}.\n"
                    "4. Horizon & Factor Alignment: Explain how the {investment_type} horizon and {focus_type} focus justify the rating.\n"
                    "5. Decision Change Triggers: Specific thresholds for upgrades or downgrades.\n\n"
                    "Be direct, evidence-based, and institutional."
                ),
            ),
        ]
    )

    chain = prompt | llm
    return chain, parser


def compute_profile_quant_decisions(stock_analysis_data: dict, prefs_dict: dict) -> dict:
    """
    Deterministically computes final scores, score breakdowns, and BUY/HOLD/SELL
    ratings based on the user's tactical profile:
    - weights depend on focus_type (Technical 55/15/30, Fundamental 20/55/25, Sentiment 25/20/55)
    - Conservative: BUY needs higher score (75) and volatility/drawdown is penalized; Aggressive: lower BUY threshold (55)
    - Short-term emphasizes 20-day SMA/RSI/MACD; Long-term emphasizes 200-day SMA/fundamentals
    """
    risk_level = prefs_dict.get("risk_level") or "Medium"
    investment_type = prefs_dict.get("investment_type") or "Long-term"
    focus_type = prefs_dict.get("focus_type") or "Technical"

    # 1. Weights based on focus_type
    if focus_type == "Technical":
        w_tech, w_fund, w_sent = 0.55, 0.15, 0.30
    elif focus_type == "Fundamental":
        w_tech, w_fund, w_sent = 0.20, 0.55, 0.25
    elif focus_type == "Sentiment":
        w_tech, w_fund, w_sent = 0.25, 0.20, 0.55
    else:
        w_tech, w_fund, w_sent = 0.45, 0.35, 0.20

    # 2. Rating Thresholds based on risk_level
    if risk_level == "Low":  # Conservative
        buy_threshold = 75
        sell_threshold = 45
    elif risk_level == "High":  # Aggressive
        buy_threshold = 55
        sell_threshold = 35
    else:  # Medium / Moderate
        buy_threshold = 65
        sell_threshold = 40

    risk_map = {"Low": "Conservative", "Medium": "Moderate", "High": "Aggressive"}
    risk_label = risk_map.get(risk_level, risk_level)
    applied_profile = f"{risk_label} · {investment_type} · {focus_type}"

    ticker_results = {}
    tech_scores = []
    fund_scores = []
    sent_scores = []
    risk_penalties = []
    composite_scores = []
    has_missing_fundamentals = False

    for ticker, data in stock_analysis_data.items():
        tech = data.get("Technicals") or {}
        fund = data.get("Fundamentals") or {}
        sent = data.get("Sentiment") or {}
        backtest = data.get("Backtest") or {}

        # Technical Score
        raw_tech = float(tech.get("tech_score") if tech.get("tech_score") is not None else 50.0)
        rsi = float(tech.get("rsi") or 50.0)
        macd = float(tech.get("macd") or 0.0)

        tech_score = raw_tech
        ev_str = " ".join(tech.get("numerical_evidence", [])) if tech.get("numerical_evidence") else ""

        if investment_type == "Short-term":
            # Emphasize 20-day SMA, RSI, MACD
            if 40 <= rsi <= 60:
                tech_score += 4.0
            elif rsi < 30:
                tech_score += 6.0  # oversold bounce signal
            elif rsi > 70:
                tech_score -= 6.0  # overbought pullback risk

            if macd > 0:
                tech_score += 5.0
            else:
                tech_score -= 5.0

            if "above 20-day SMA" in ev_str:
                tech_score += 5.0
            elif "below 20-day SMA" in ev_str:
                tech_score -= 5.0
        else:  # Long-term
            # Emphasize 200-day SMA and broader primary trend
            if "Above 200-day SMA" in ev_str:
                tech_score += 8.0
            elif "Below 200-day SMA" in ev_str:
                tech_score -= 10.0

        tech_score = max(0.0, min(100.0, tech_score))

        # Fundamental Score
        fund_avail = fund.get("available", False)
        if not fund_avail or fund.get("fundamental_score") is None:
            has_missing_fundamentals = True
            fund_score = 50.0  # Neutral baseline
        else:
            fund_score = float(fund["fundamental_score"])
            if investment_type == "Long-term" and fund_score >= 60:
                fund_score = min(100.0, fund_score + 5.0)

        # Sentiment Score (-1.0 to 1.0 mapped to 0 to 100)
        raw_sent = float(sent.get("sentiment_score", 0.0))
        sent_score = max(0.0, min(100.0, (raw_sent + 1.0) * 50.0))

        # Risk Penalties (Volatility & Drawdown)
        max_dd = float(backtest.get("max_drawdown") or 0.0)
        vol = float(tech.get("volatility") or 0.0)

        penalty = 0.0
        if risk_level == "Low":  # Conservative: penalize drawdown & volatility heavily
            if max_dd > 0.15:
                penalty += min(15.0, (max_dd - 0.15) * 50.0)
            if vol > 0.25:
                penalty += min(10.0, (vol - 0.25) * 40.0)
        elif risk_level == "Medium":
            if max_dd > 0.25:
                penalty += min(8.0, (max_dd - 0.25) * 30.0)
        elif risk_level == "High":  # Aggressive: high risk tolerance
            if max_dd > 0.40:
                penalty += min(5.0, (max_dd - 0.40) * 15.0)

        ticker_composite = (w_tech * tech_score) + (w_fund * fund_score) + (w_sent * sent_score) - penalty
        ticker_final = max(0.0, min(100.0, ticker_composite))

        if ticker_final >= buy_threshold:
            ticker_rec = "BUY"
        elif ticker_final < sell_threshold:
            ticker_rec = "SELL"
        else:
            ticker_rec = "HOLD"

        tech_scores.append(tech_score)
        fund_scores.append(fund_score)
        sent_scores.append(sent_score)
        risk_penalties.append(penalty)
        composite_scores.append(ticker_final)

        ticker_results[ticker] = {
            "score": round(ticker_final),
            "recommendation": ticker_rec,
            "technical": round(tech_score),
            "fundamental": round(fund_score),
            "sentiment": round(sent_score),
            "penalty": round(penalty, 1),
            "max_drawdown_pct": round(max_dd * 100, 1),
        }

    # Aggregate Portfolio-level metrics
    n = max(len(composite_scores), 1)
    avg_final = sum(composite_scores) / n
    final_score = round(avg_final)

    if final_score >= buy_threshold:
        recommendation = "BUY"
    elif final_score < sell_threshold:
        recommendation = "SELL"
    else:
        recommendation = "HOLD"

    avg_penalty = sum(risk_penalties) / n
    risk_subscore = max(0, min(100, round(100 - avg_penalty * 3)))

    score_breakdown = {
        "technical": round(sum(tech_scores) / n),
        "fundamental": round(sum(fund_scores) / n),
        "sentiment": round(sum(sent_scores) / n),
        "risk": risk_subscore,
    }

    spread = max(composite_scores) - min(composite_scores) if len(composite_scores) > 1 else 10.0
    confidence = round(max(40.0, min(95.0, 90.0 - (spread * 0.5) - (15.0 if has_missing_fundamentals else 0.0))))

    fundamental_notice = None
    if focus_type == "Fundamental" and has_missing_fundamentals:
        fundamental_notice = (
            "Fundamental focus is running without complete fundamental valuation data due to "
            "market provider rate limits. Valuation weights are supplemented with quantitative momentum."
        )

    return {
        "applied_profile": applied_profile,
        "weights_info": f"Technical {int(w_tech * 100)}% / Fundamental {int(w_fund * 100)}% / Sentiment {int(w_sent * 100)}%",
        "thresholds_info": f"BUY >= {buy_threshold}, SELL < {sell_threshold}",
        "buy_threshold": buy_threshold,
        "sell_threshold": sell_threshold,
        "weights": {"technical": w_tech, "fundamental": w_fund, "sentiment": w_sent},
        "final_score": final_score,
        "recommendation": recommendation,
        "score_breakdown": score_breakdown,
        "confidence_score": confidence,
        "has_missing_fundamentals": has_missing_fundamentals,
        "fundamental_notice": fundamental_notice,
        "ticker_results": ticker_results,
    }


def _parse_report_json(raw_text: str, parser: JsonOutputParser) -> dict:
    """Robustly parses LLM response into the ReportOutput schema dictionary with fallbacks."""
    if not raw_text or not raw_text.strip():
        return {
            "report": "No report content generated.",
            "final_score": 50,
            "score_breakdown": {"technical": 50, "fundamental": 50, "sentiment": 50, "risk": 50},
            "recommendation": "HOLD",
            "confidence_score": 50,
            "strategy_accuracy": 50.0,
            "decision_triggers": [],
        }

    # 1. Try standard LangChain JsonOutputParser
    try:
        data = parser.parse(raw_text)
        if isinstance(data, dict):
            return data
    except Exception as err:
        logger.debug(f"[Report] Parser parse failed: {err}")

    # 2. Try direct json.loads
    try:
        data = json.loads(raw_text)
        if isinstance(data, dict):
            return data
    except Exception as err:
        logger.debug(f"[Report] Direct json loads failed: {err}")

    # 3. Try markdown fenced code block: ```json ... ```
    try:
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, re.DOTALL)
        if match:
            data = json.loads(match.group(1))
            if isinstance(data, dict):
                return data
    except Exception as err:
        logger.debug(f"[Report] Regex json markdown block extraction failed: {err}")

    # 4. Try greedy outermost braces: {...}
    try:
        match = re.search(r"(\{.*\})", raw_text, re.DOTALL)
        if match:
            data = json.loads(match.group(1))
            if isinstance(data, dict):
                return data
    except Exception as err:
        logger.debug(f"[Report] Regex outer brace extraction failed: {err}")

    # 5. Safe fallback: wrap the raw LLM output into ReportOutput schema so UI never fails
    rec = "HOLD"
    upper = raw_text.upper()
    if "RECOMMENDATION: BUY" in upper or "**BUY**" in upper:
        rec = "BUY"
    elif "RECOMMENDATION: SELL" in upper or "**SELL**" in upper:
        rec = "SELL"

    return {
        "report": raw_text.strip(),
        "final_score": 50,
        "score_breakdown": {"technical": 50, "fundamental": 50, "sentiment": 50, "risk": 50},
        "recommendation": rec,
        "confidence_score": 50,
        "strategy_accuracy": 50.0,
        "decision_triggers": [],
    }


def _process_single_ticker(ticker: str) -> tuple:
    """Helper function to analyze a single ticker during parallel report generation."""
    logger.info(f"[Perf] Starting analysis for {ticker}...")
    start_time = time.time()
    try:
        df = fetch_stock_data(ticker, period="1y")
        if df is None or df.empty:
            logger.warning(f"[Perf] No data for {ticker}, skipping.")
            return ticker, None

        tech_df = calculate_technical_indicators(df)
        tech_summary = generate_technical_summary(tech_df)
        if hasattr(tech_summary, "dict"):
            tech_summary = tech_summary.dict()

        sent_summary = analyze_sentiment(ticker)
        if hasattr(sent_summary, "dict"):
            sent_summary = sent_summary.dict()

        fund_summary = evaluate_fundamentals(ticker)
        if hasattr(fund_summary, "dict"):
            fund_summary = fund_summary.dict()

        backtest_summary = run_institutional_backtest(df, ticker)

        # Compute empirical max drawdown from prices
        if "Close" in df.columns:
            cummax = df["Close"].cummax()
            drawdown = (df["Close"] - cummax) / cummax
            max_dd = abs(float(drawdown.min())) if not drawdown.empty else 0.0
            backtest_summary["max_drawdown"] = round(max_dd, 4)

        elapsed = time.time() - start_time
        logger.info(f"[Perf] Completed {ticker} in {elapsed:.2f}s")
        return ticker, {
            "Technicals": tech_summary,
            "Fundamentals": fund_summary,
            "Sentiment": sent_summary,
            "Backtest": backtest_summary,
        }
    except Exception as e:
        logger.error(f"[Perf] Error processing {ticker}: {e}")
        return ticker, None


def generate_user_report(db: Session, current_user: User) -> dict:
    """
    Generates a personalized stock advisory report for the authenticated user.
    Uses deterministic profile-driven quantitative calculations for scores and ratings,
    with LLM synthesis producing the explanation.
    """
    # ── 1. Load User Preferences ──────────────────────────────────────────────
    prefs = db.query(UserPreference).filter(UserPreference.user_id == current_user.id).first()
    if not prefs:
        prefs_dict = {
            "risk_level": "Medium",
            "investment_type": "Long-term",
            "focus_type": "Technical",
            "budget_range": "Not specified",
            "expected_return": "Not specified",
        }
    else:
        prefs_dict = {
            "risk_level": prefs.risk_level or "Medium",
            "investment_type": prefs.investment_type or "Long-term",
            "focus_type": prefs.focus_type or "Technical",
            "budget_range": prefs.budget_range or "Not specified",
            "expected_return": prefs.expected_return or "Not specified",
        }

    # ── 2. Load Watchlist ─────────────────────────────────────────────────────
    watchlist = db.query(Watchlist).filter(Watchlist.user_id == current_user.id).all()
    if not watchlist:
        return {"error": "No stocks in watchlist. Please add stocks before generating a report."}

    tickers = [item.ticker for item in watchlist]
    stock_analysis_data = {}

    # ── 3. Run Analysis Pipeline Parallelized ───────────────────────────────
    logger.info(f"[Perf] Starting parallel analysis for {len(tickers)} tickers...")
    overall_start = time.time()

    with ThreadPoolExecutor(max_workers=min(len(tickers), 10)) as executor:
        future_to_ticker = {executor.submit(_process_single_ticker, ticker): ticker for ticker in tickers}
        for future in as_completed(future_to_ticker):
            ticker, result = future.result()
            if result:
                stock_analysis_data[ticker] = result

    overall_elapsed = time.time() - overall_start
    logger.info(f"[Perf] Total analysis completed in {overall_elapsed:.2f}s")

    if not stock_analysis_data:
        return {"error": "Could not fetch data for any stock in your watchlist."}

    # ── 4. Deterministic Profile-Based Quantitative Computation ────────────
    quant_decisions = compute_profile_quant_decisions(stock_analysis_data, prefs_dict)

    # ── 5. Groq Synthesis with Structured Output ───────────────────────────
    last_err = None
    for model_candidate in [PRIMARY_MODEL, FALLBACK_MODEL]:
        try:
            chain, parser = _build_report_chain(model=model_candidate)
            ai_msg = chain.invoke(
                {
                    "applied_profile": quant_decisions["applied_profile"],
                    "risk_level": prefs_dict["risk_level"],
                    "investment_type": prefs_dict["investment_type"],
                    "focus_type": prefs_dict["focus_type"],
                    "budget_range": prefs_dict["budget_range"],
                    "expected_return": prefs_dict["expected_return"],
                    "weights_info": quant_decisions["weights_info"],
                    "thresholds_info": quant_decisions["thresholds_info"],
                    "computed_score": quant_decisions["final_score"],
                    "computed_recommendation": quant_decisions["recommendation"],
                    "computed_breakdown": json.dumps(quant_decisions["score_breakdown"]),
                    "deterministic_results": json.dumps(quant_decisions["ticker_results"], indent=2),
                    "stock_data": json.dumps(stock_analysis_data, indent=2, default=str),
                    "format_instructions": parser.get_format_instructions(),
                }
            )
            raw_text = ai_msg.content if hasattr(ai_msg, "content") else str(ai_msg)
            result = _parse_report_json(raw_text, parser)

            # Ensure final quantitative decisions are strictly deterministic
            result["final_score"] = quant_decisions["final_score"]
            result["recommendation"] = quant_decisions["recommendation"]
            result["score_breakdown"] = quant_decisions["score_breakdown"]
            result["confidence_score"] = quant_decisions["confidence_score"]
            result["applied_profile"] = quant_decisions["applied_profile"]
            result["fundamental_notice"] = quant_decisions["fundamental_notice"]
            result["has_missing_fundamentals"] = quant_decisions["has_missing_fundamentals"]
            result["weights"] = quant_decisions["weights"]
            result["buy_threshold"] = quant_decisions["buy_threshold"]
            result["sell_threshold"] = quant_decisions["sell_threshold"]

            result["model"] = model_candidate
            result["tickers"] = list(stock_analysis_data.keys())
            result["generated_at"] = datetime.now().strftime("%I:%M %p").lstrip("0")
            return result
        except Exception as e:
            logger.warning(f"[Report] Structured synthesis failed with {model_candidate}: {e}")
            last_err = e

    return {"error": f"Report generation failed: {last_err!s}"}
