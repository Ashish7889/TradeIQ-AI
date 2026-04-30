"""
StockSense AI — Sentiment Analysis Service
==========================================
This module handles all news/sentiment data retrieval and scoring.

Two separate concerns:
  1. Data Retrieval: fetch_news_headlines() → returns raw headline strings
     used by BOTH the LangChain pipeline (as Documents) AND the direct API endpoint.

  2. VADER Scoring: score_sentiment_with_vader() → baseline algorithmic score.
     Fast, deterministic, no LLM dependency.

  3. Full Sentiment Analysis (direct API endpoint): analyze_sentiment()
     Uses Groq via LangChain LLMChain, falls back to VADER.

The langchain_agent.py orchestrator calls fetch_news_headlines() and
score_sentiment_with_vader() directly to build Documents and get baseline scores.
"""

import os
import logging
import requests
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session
from models import Stock, SentimentData
from datetime import datetime
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
import yfinance as yf
import json

# ── LangChain ─────────────────────────────────────────────────────────────────
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)
analyzer = SentimentIntensityAnalyzer()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")


# =============================================================================
#  DATA RETRIEVAL LAYER
# =============================================================================

def fetch_news_headlines(ticker: str) -> list[str]:
    """
    Fetches the latest news headlines for a given ticker.
    Primary source: Yahoo Finance via yfinance.
    Fallback: Finviz web scraper.
    Returns a list of headline strings (used as LangChain Document content).
    """
    ticker = ticker.upper()
    headlines = []

    # Primary: Yahoo Finance
    try:
        stock = yf.Ticker(ticker)
        news = stock.news
        if news:
            for item in news[:10]:
                title = item.get("title", "")
                if title:
                    headlines.append(title)
    except Exception as e:
        logger.warning(f"Yahoo Finance news fetch failed for {ticker}: {e}")

    # Fallback: Finviz scraper
    if not headlines:
        headlines = _fetch_finviz_news(ticker)

    return headlines[:10]  # Limit to 10 headlines


def _fetch_finviz_news(ticker: str) -> list[str]:
    """Fallback news scraper from Finviz."""
    url = f"https://finviz.com/quote.ashx?t={ticker}"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(url, headers=headers, timeout=5)
        soup = BeautifulSoup(response.text, "html.parser")
        news_table = soup.find(id="news-table")
        if not news_table:
            return []
        headlines = []
        for row in news_table.findAll("tr"):
            a_tag = row.find("a")
            if a_tag:
                headlines.append(a_tag.text.strip())
        return headlines[:10]
    except Exception as e:
        logger.error(f"Finviz scraping failed for {ticker}: {e}")
        return []


# =============================================================================
#  VADER BASELINE SCORER (Algorithmic — No LLM)
# =============================================================================

def score_sentiment_with_vader(headlines: list[str]) -> float:
    """
    Computes a baseline sentiment score using VADER (Valence Aware Dictionary
    and sEntiment Reasoner). Returns a float from -1.0 to 1.0.

    VADER is optimized for short, social-media-style text (news headlines are ideal).
    This provides a deterministic algorithmic check before LangChain/LLM scoring.
    """
    if not headlines:
        return 0.0
    total = sum(analyzer.polarity_scores(h)["compound"] for h in headlines)
    return total / len(headlines)


# =============================================================================
#  FULL SENTIMENT ANALYSIS (used by direct /sentiment API endpoint)
# =============================================================================

def analyze_sentiment(ticker: str, db: Session = None) -> dict | None:
    """
    Hybrid Elite Sentiment Engine:
    1. VADER baseline (Institutional Algorithmic)
    2. Optional Groq Refinement (Semantic Deep-Dive)
    3. Auto-Fallback: If Groq is 429/Exhausted, gracefully use VADER.
    """
    ticker = ticker.upper()
    try:
        headlines = fetch_news_headlines(ticker)
        if not headlines:
            return None

        summary_text = " | ".join(headlines[:5])
        vader_score = score_sentiment_with_vader(headlines)
        
        # Default results to VADER baseline
        avg_score = vader_score
        label = "Positive" if avg_score > 0.15 else "Negative" if avg_score < -0.15 else "Neutral"
        source = "VADER (Algorithmic)"

        # Hybrid Decision: Only use Groq for ambiguous cases OR if we want deep-dive precision
        # Threshold: -0.2 to 0.2 is often ambiguous for simple keyword models
        is_ambiguous = -0.2 <= vader_score <= 0.2

        if is_ambiguous:
            try:
                llm = ChatGroq(
                    model="llama-3.3-70b-versatile",
                    api_key=GROQ_API_KEY,
                    temperature=0.0,
                    # Short timeout to keep the report fast
                    timeout=10,
                )
                prompt = ChatPromptTemplate.from_messages([
                    ("system", "You are a financial news sentiment analyst. Output ONLY valid JSON."),
                    ("human", (
                        "Analyze these news headlines for {ticker} and return JSON:\n"
                        "{headlines}\n\n"
                        "Return exactly:\n"
                        "{{\"sentiment_score\": <float -1.0 to 1.0>, \"sentiment_label\": \"Positive\"|\"Neutral\"|\"Negative\"}}"
                    )),
                ])
                parser = JsonOutputParser()
                chain = prompt | llm | parser
                result = chain.invoke({"ticker": ticker, "headlines": summary_text})
                
                avg_score = float(result.get("sentiment_score", vader_score))
                label = result.get("sentiment_label", label)
                source = "Groq Llama 3 (Hybrid Refinement)"
                logger.info(f"[Sentiment] Groq refined {ticker} sentiment.")
                
            except Exception as e:
                # GRACEFUL FALLBACK: If Groq is 429 (quota) or 503 (busy), use VADER.
                # No crash allowed for the user.
                logger.warning(f"[Sentiment] Groq fallback for {ticker} (using VADER): {e}")
                source = "VADER (Fallback)"

        # Persist to DB if session provided
        if db:
            try:
                from models import Stock, SentimentData
                db_stock = db.query(Stock).filter(Stock.ticker == ticker).first()
                if db_stock:
                    record = SentimentData(
                        stock_id=db_stock.id,
                        sentiment_score=avg_score,
                        sentiment_label=label,
                        headline=f"[{source}] {summary_text}",
                        timestamp=datetime.utcnow(),
                    )
                    db.add(record)
                    db.commit()
            except Exception as db_err:
                logger.error(f"DB persistence failed for sentiment: {db_err}")

        return {
            "sentiment_score": round(avg_score, 2),
            "sentiment_label": label,
            "summary_text": summary_text,
            "vader_score": round(vader_score, 3),
            "source": source
        }

    except Exception as e:
        logger.error(f"Sentiment analysis error for {ticker}: {e}")
        return None

    except Exception as e:
        logger.error(f"Sentiment analysis error for {ticker}: {e}")
        return None
