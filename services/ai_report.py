"""
StockSense AI — AI Report Generation Service
=============================================
Upgraded to use LangChain LLMChain + ChatPromptTemplate + StrOutputParser.
Replaces direct google.generativeai SDK calls.

This service handles the /report/generate endpoint (watchlist-based report).
For the full sequential pipeline report, see langchain_agent.py.
"""

import os
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

# ── LangChain ─────────────────────────────────────────────────────────────────
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, Field

# ── Project Services ─────────────────────────────────────────────────────────
from sqlalchemy.orm import Session
from models import Watchlist, UserPreference, User
from services.stock_data import fetch_stock_data
from services.technical import calculate_technical_indicators, generate_technical_summary
from services.sentiment import analyze_sentiment
from services.fundamental import evaluate_fundamentals
from services.quant_backtest import run_institutional_backtest

load_dotenv()
logger = logging.getLogger(__name__)
GROQ_API_KEY = os.getenv("GROQ_API_KEY")


class ReportOutput(BaseModel):
    report: str = Field(description="The full Markdown report text with sections and highlights.")
    final_score: int = Field(description="Weighted final quant score (0-100).")
    score_breakdown: dict = Field(description="Breakdown: {technical, fundamental, sentiment, risk} (0-100 each).")
    recommendation: str = Field(description="BUY, HOLD, or SELL.")
    confidence_score: int = Field(description="0-100% confidence level.")
    strategy_accuracy: float = Field(description="1-year Backtested Strategy Accuracy (%).")
    decision_triggers: list = Field(description="Specific data triggers that would change this rating.")


def _build_report_chain():
    """Builds the Top-Tier Quant Report Chain returning structured JSON."""
    llm = ChatGroq(
        model="llama-3.3-70b-versatile",
        api_key=GROQ_API_KEY,
        temperature=0.05,
    )
    
    parser = JsonOutputParser(pydantic_object=ReportOutput)

    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are QuantCore, an institutional-grade market reasoning engine and senior buy-side analyst. "
            "You produce precise, evidence-anchored, professional investment research reports. "
            "CRITICAL RULES: (1) Use only supplied data — never invent metrics, prices, or events. "
            "(2) Every statement must cite a specific data point from the input. "
            "(3) Never use filler phrases like 'mixed picture' or 'various factors'. "
            "(4) If a metric is missing, state it explicitly and reduce confidence accordingly. "
            "(5) When signals conflict, explain the conflict and default to the risk-controlled view. "
            "(6) Sentiment score is -1.0 to 1.0 — map to 0-100 for score_breakdown (0.0=50, -1.0=0, 1.0=100). "
            "(7) final_score must be a weighted composite: Technical 45% + Fundamental 35% + Sentiment 20%. "
            "(8) confidence_score must reflect signal agreement and data completeness, not just sentiment. "
            "Output structured JSON only.\n\n"
            "{format_instructions}"
        )),
        ("human", (
            "Generate a personalized quant research report for the following investment profile.\n\n"
            "=== INVESTOR PROFILE ===\n"
            "Risk Level: {risk_level}\n"
            "Focus Area: {focus_type}\n\n"
            "=== PORTFOLIO DATA ===\n"
            "{stock_data}\n\n"
            "=== INSTITUTIONAL SCORING RULES ===\n"
            "1. **Sentiment Mapping**: Raw sentiment data is -1.0 to 1.0. You MUST map this to a 0-100 scale in 'score_breakdown'. (0.0 = 50/100, -1.0 = 0/100, 1.0 = 100/100).\n"
            "2. **Final Score**: 0-100 based on weighted Technical, Fundamental, and Sentiment data.\n\n"
            "=== REPORT STRUCTURE INSTRUCTIONS ===\n"
            "1. **Market Overview**: 2-3 direct, data-backed sentences.\n"
            "2. **Stock Comparison Table**: Markdown pipe table: Ticker | Score | Accuracy | Rec | Key Signal.\n"
            "3. **Top Picks**: Justify using raw numbers from data.\n"
            "4. **Strategy Backtest**: Reference the 1-year statistical accuracy for the tickers.\n"
            "5. **Decision Change Triggers**: Explicitly list data points for upgrades/downgrades.\n\n"
            "Use **bolding** for all key metrics. Be direct. Be precise."
        )),
    ])

    chain = prompt | llm | parser
    return chain, parser


def _process_single_ticker(ticker: str) -> tuple:
    """Helper function to analyze a single ticker during parallel report generation."""
    logger.info(f"[Perf] Starting analysis for {ticker}...")
    start_time = time.time()
    try:
        # We don't pass 'db' here because SQLAlchemy sessions are NOT thread-safe.
        # fetch_stock_data will just return the DataFrame without updating the DB.
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

    Pipeline:
    1. Load user preferences from DB
    2. Load user watchlist from DB
    3. For each ticker: fetch market data → technical → fundamental → sentiment
    4. Send all data to Groq via LangChain LLMChain PromptTemplate
    5. Return structured Markdown report

    Returns:
        {"report": str}  or  {"error": str}
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

    # ── 4. Groq Synthesis with Structured Output ───────────────────────────
    try:
        chain, parser = _build_report_chain()
        result = chain.invoke({
            "risk_level": prefs_dict["risk_level"],
            "focus_type": prefs_dict["focus_type"],
            "stock_data": json.dumps(stock_analysis_data, indent=2, default=str),
            "format_instructions": parser.get_format_instructions(),
        })
        # result is already a dict per ReportOutput schema
        return result

    except Exception as e:
        logger.error(f"[Report] Structured synthesis failed: {e}")
        return {"error": f"Report generation failed: {str(e)}"}
