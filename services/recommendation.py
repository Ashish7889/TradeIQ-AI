"""
StockSense AI — Recommendation Engine
======================================
Upgraded to use LangChain ChatGroq + ChatPromptTemplate + JsonOutputParser.
Falls back to a deterministic algorithmic heuristic if the LLM chain fails.
"""

import os
import json
import logging
from dotenv import load_dotenv

# ── LangChain ─────────────────────────────────────────────────────────────────
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

load_dotenv()
logger = logging.getLogger(__name__)
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
PRIMARY_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
FALLBACK_MODEL = os.getenv("GROQ_FALLBACK_MODEL", "openai/gpt-oss-20b")


# =============================================================================
#  LANGCHAIN RECOMMENDATION CHAIN
# =============================================================================

def _build_recommendation_chain(model: str = PRIMARY_MODEL):
    """
    Builds a LangChain chain for BUY/HOLD/SELL recommendation.
    Uses: ChatGroq → ChatPromptTemplate → JsonOutputParser
    """
    llm = ChatGroq(
        model=model,
        api_key=GROQ_API_KEY,
        temperature=0.0,
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are an elite Wall Street quantitative analyst. You are brutally honest. "
            "You do not sugarcoat results. If technical indicators are bearish, you MUST say SELL or HOLD. "
            "If a P/E ratio is dangerously high, you MUST reflect that. "
            "You return ONLY valid JSON. No markdown. No commentary outside the JSON."
        )),
        ("human", (
            "Analyze the following data and generate a trading recommendation.\n\n"
            "Technical Analysis:\n{technical_data}\n\n"
            "Fundamental Analysis:\n{fundamental_data}\n\n"
            "News Sentiment:\n{sentiment_data}\n\n"
            "Return ONLY a JSON object with this EXACT schema:\n"
            "{{\n"
            "  \"recommendation\": \"BUY\" | \"HOLD\" | \"SELL\",\n"
            "  \"confidence_score\": <float 0-100>,\n"
            "  \"trend_direction\": \"Bullish\" | \"Bearish\" | \"Neutral\",\n"
            "  \"risk_level\": \"Low\" | \"Medium\" | \"High\",\n"
            "  \"explanation_text\": \"<3-4 sentences citing exact data points>\",\n"
            "  \"portfolio_allocation\": \"<e.g. Max 5% Portfolio Weight or 0% (Avoid)>\",\n"
            "  \"price_prediction\": \"<e.g. 65% Probability of upward trend within 30 days>\",\n"
            "  \"score_breakdown\": {{\n"
            "    \"technical\": <float 0-100>,\n"
            "    \"fundamental\": <float 0-100>,\n"
            "    \"sentiment\": <float 0-100>\n"
            "  }}\n"
            "}}"
        )),
    ])

    parser = JsonOutputParser()
    return prompt | llm | parser


# =============================================================================
#  PUBLIC FUNCTION
# =============================================================================

def generate_recommendation(technical_data: dict, sentiment_data: dict, fundamental_data: dict) -> dict:
    """
    Primary recommendation engine.
    1. Attempts LangChain LLMChain with structured JsonOutputParser
    2. Falls back to deterministic algorithmic heuristic if chain fails

    Args:
        technical_data:  Output from generate_technical_summary()
        sentiment_data:  Output from analyze_sentiment()
        fundamental_data: Output from evaluate_fundamentals()

    Returns:
        RecommendationOut-compatible dict
    """
    # ── Try LangChain LLMChain ────────────────────────────────────────────────
    for model_candidate in [PRIMARY_MODEL, FALLBACK_MODEL]:
        try:
            chain = _build_recommendation_chain(model=model_candidate)
            result = chain.invoke({
                "technical_data": json.dumps(technical_data or {}, default=str),
                "fundamental_data": json.dumps(fundamental_data or {}, default=str),
                "sentiment_data": json.dumps(sentiment_data or {}, default=str),
            })

            required_keys = [
                "recommendation", "confidence_score", "trend_direction",
                "risk_level", "explanation_text", "portfolio_allocation",
                "price_prediction", "score_breakdown"
            ]
            if all(k in result for k in required_keys):
                logger.info(f"LangChain recommendation chain succeeded with {model_candidate}: {result['recommendation']}")
                return result
            else:
                logger.warning(f"LangChain response with {model_candidate} missing required keys: {result}")
        except Exception as e:
            logger.warning(f"LangChain recommendation chain failed with {model_candidate}: {e}")

    logger.warning("All LLM recommendation attempts failed, using algorithmic heuristic.")
    return _fallback_algorithmic_recommendation(technical_data, sentiment_data, fundamental_data)


# =============================================================================
#  ALGORITHMIC FALLBACK
# =============================================================================

def _fallback_algorithmic_recommendation(
    technical_data: dict, sentiment_data: dict, fundamental_data: dict
) -> dict:
    """
    Deterministic algorithmic fallback.
    Weights: Technical 35%, Fundamental 30%, Sentiment 25%, Risk 10%
    """
    explanations = []
    risk_level = "Medium"
    risk_adjustment = 0

    # Technical score (35%)
    tech_score = 50
    if technical_data:
        interp = technical_data.get("interpretations", {})
        trend = interp.get("trend", "Neutral")
        rsi = interp.get("rsi", "Neutral")
        macd = interp.get("macd", "Neutral")
        vol = technical_data.get("volatility", 0) or 0

        if trend == "Bullish":
            tech_score += 20
        elif trend == "Bearish":
            tech_score -= 20
        if rsi == "Oversold":
            tech_score += 15
        elif rsi == "Overbought":
            tech_score -= 15
        if macd == "Bullish Crossover":
            tech_score += 15
        elif macd == "Bearish Crossover":
            tech_score -= 15

        tech_score = max(0, min(100, tech_score))

        if vol > 40:
            risk_adjustment = -10
            risk_level = "High"
        elif vol < 15:
            risk_adjustment = 5
            risk_level = "Low"

        explanations.append(f"Technical setup is {trend}. RSI is {rsi}. MACD shows {macd}.")
    else:
        explanations.append("Technical data unavailable.")

    # Fundamental score (30%)
    fund_score = 50
    if fundamental_data:
        fund_score = fundamental_data.get("fundamental_score", 50)
        if fund_score > 70:
            explanations.append("Strong fundamental metrics.")
        elif fund_score < 40:
            explanations.append("Weak fundamental metrics.")
    else:
        explanations.append("Fundamental data unavailable.")

    # Sentiment score (25%)
    sent_score = 50
    if sentiment_data:
        raw = sentiment_data.get("sentiment_score", 0.0) or 0.0
        sent_score = (raw + 1) * 50
        label = sentiment_data.get("sentiment_label", "Neutral")
        explanations.append(f"News sentiment is {label}.")
    else:
        explanations.append("Sentiment data unavailable.")

    # Combined
    final_score = (tech_score * 0.35) + (fund_score * 0.30) + (sent_score * 0.25) + risk_adjustment
    final_score = max(0, min(100, final_score))

    if final_score >= 65:
        rec = "BUY"
    elif final_score <= 40:
        rec = "SELL"
    else:
        rec = "HOLD"

    trend_dir = (technical_data or {}).get("interpretations", {}).get("trend", "Neutral")

    return {
        "recommendation": rec,
        "confidence_score": round(final_score, 2),
        "trend_direction": trend_dir,
        "risk_level": risk_level,
        "explanation_text": " ".join(explanations),
        "portfolio_allocation": "Heuristic fallback — LangChain chain unavailable",
        "price_prediction": "Heuristic fallback — LangChain chain unavailable",
        "score_breakdown": {
            "technical": round(tech_score, 2),
            "fundamental": round(fund_score, 2),
            "sentiment": round(sent_score, 2),
        },
    }
