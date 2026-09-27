"""
StockSense AI — QuantCore Sequential Analysis Pipeline v2
==========================================================
Architecture:

  User Input
     ↓
  Yahoo Finance API  (Stage 1: Market Data Fetch)
     ↓
  Algorithmic Engines:
     ├─➜ Stage 2: Technical Analysis   (RSI, SMA, MACD, Golden/Death Cross)
     ├─➜ Stage 3: Fundamental Analysis (P/E, EPS, Revenue, Margins, D/E)
     ├─➜ Stage 4: Sentiment Analysis   (VADER + Groq LLMChain hybrid)
     ├─➜ Stage 5: Risk Assessment      (VaR, Beta, Sharpe, Drawdown)
     └─➜ Stage 6: Backtest             (SMA Crossover 20/50 strategy)
     ↓
  Stage 7: QuantCore Decision Engine (Groq via LangChain JsonOutputParser)
     ↓
  Structured JSON: Conviction score, triggers, key levels, portfolio actions
"""

import os
import json
import logging
import time
from typing import Optional
from datetime import datetime

# ── LangChain Core ────────────────────────────────────────────────────────────
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser
from langchain_core.documents import Document

# ── Project Services (Algorithmic) ───────────────────────────────────────────
from services.stock_data import fetch_stock_data
from services.technical import calculate_technical_indicators, generate_technical_summary
from services.fundamental import evaluate_fundamentals
from services.sentiment import fetch_news_headlines, score_sentiment_with_vader
from services.risk_assessment import calculate_risk_metrics
from services.quant_backtest import run_institutional_backtest

# ── Environment ───────────────────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv()

logger = logging.getLogger(__name__)
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# ── Model Config ─────────────────────────────────────────────────────────────
PRIMARY_MODEL   = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
FALLBACK_MODEL  = os.getenv("GROQ_FALLBACK_MODEL", "openai/gpt-oss-20b")



def invoke_with_retry(chain, inputs: dict, max_retries: int = 3, base_delay: float = 5.0):
    """
    Invokes a LangChain chain with exponential backoff retry.
    Handles RESOURCE_EXHAUSTED (429) and rate limit errors gracefully.
    Falls back automatically between primary and fallback models.
    """
    last_error = None
    for attempt in range(max_retries):
        try:
            return chain.invoke(inputs)
        except Exception as e:
            err_str = str(e).lower()
            is_quota = any(kw in err_str for kw in [
                "resource_exhausted", "429", "quota", "rate_limit", "rate limit"
            ])
            if is_quota:
                wait = base_delay * (2 ** attempt)   # 5s → 10s → 20s
                logger.warning(
                    f"[QuantCore] Rate limit hit (attempt {attempt+1}/{max_retries}). "
                    f"Retrying in {wait:.0f}s..."
                )
                time.sleep(wait)
                last_error = e
            else:
                raise   # non-quota errors bubble up immediately
    raise last_error  # all retries exhausted


# =============================================================================
#  STAGE 4 HELPER — Sentiment LangChain (only LLM stage before QuantCore)
# =============================================================================

def _build_sentiment_chain(model: str = PRIMARY_MODEL):
    llm = ChatGroq(
        model=model,
        api_key=GROQ_API_KEY,
        temperature=0.0,
    )
    sentiment_prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are a senior financial news analyst specializing in quantitative sentiment scoring. "
            "You analyze news headlines with extreme precision. "
            "Output ONLY valid JSON. No markdown. No explanation outside the JSON."
        )),
        ("human", (
            "Analyze the following recent news headlines for the stock ticker: {ticker}\n\n"
            "Headlines:\n{headlines}\n\n"
            "Return ONLY this JSON:\n"
            "{{\n"
            "  \"sentiment_score\": <float -1.0 to 1.0>,\n"
            "  \"sentiment_label\": \"Positive\" | \"Neutral\" | \"Negative\",\n"
            "  \"reasoning\": \"<1-2 sentence explanation citing specific headlines>\"\n"
            "}}"
        ))
    ])
    return sentiment_prompt | llm | JsonOutputParser()


# =============================================================================
#  STAGE 7 — QuantCore Institutional Decision Engine
# =============================================================================

QUANTCORE_SYSTEM = """You are QuantCore, an institutional-grade market reasoning engine and senior buy-side analyst with 20+ years of experience across equity research, quantitative trading, and portfolio management at a top-tier investment bank.

Your job is to transform structured quantitative inputs into precise, high-conviction, actionable investment intelligence — exactly how a Goldman Sachs MD would present to a portfolio committee.

You understand deeply:
- Multi-timeframe technical structure (trend, momentum, mean reversion, volume confirmation)
- Fundamental valuation across growth, value, and GARP frameworks
- Sentiment regime analysis (news flow, social momentum, institutional positioning signals)
- Risk-adjusted portfolio construction and position sizing
- Macro regime overlays (rate environment, VIX regime, sector rotation)
- Invalidation logic and stop-loss framework
- Earnings and catalyst event risk

You are NOT a chatbot. You are a decision engine that generates institutional-quality equity research.

=== CRITICAL RULES (NEVER VIOLATE) ===
1. Use ONLY the data provided in the input. Never invent prices, ratios, events, indicators, or news.
2. If any metric is missing or null, explicitly state it is unavailable and reduce confidence proportionally.
3. Never give generic advice. Every statement must be anchored to a specific supplied data point.
4. Never repeat raw indicator values without interpretation. Translate numbers into meaning.
5. Every conclusion must cite the specific evidence that supports it.
6. When signals conflict, explicitly name the conflict, explain why it exists, and default to the more conservative risk-controlled view.
7. Never express certainty unless all signals — technical, fundamental, and sentiment — agree and data is complete.
8. If volatility is elevated (annualized_vol > 35%) or trend is unclear, increase Technical weight to 55%, reduce others proportionally.
9. If fundamental_score is below 30 or above 80, increase Fundamental weight to 45%, reduce Technical to 35%.
10. If sentiment_score magnitude is above 0.6 AND it is supported by volume confirmation, increase Sentiment weight to 30%, reduce Technical to 35%.
11. Output must be valid JSON ONLY. No markdown. No commentary outside the JSON object. No code fences.

=== ANALYSIS FRAMEWORK (EXECUTE IN ORDER) ===
Step 1 — Market Regime Detection: Classify as Trending_Bull, Trending_Bear, High_Volatility, Sideways_Consolidation, or Recovery based on price vs SMAs, volatility, and backtest performance.
Step 2 — Per-Stock Technical Evaluation: Assess momentum (RSI, MACD histogram), trend structure (price vs SMA20/50/200), and Golden/Death Cross signals. Identify precise support and resistance from SMA levels and 52-week range.
Step 3 — Per-Stock Fundamental Evaluation: Assess valuation (P/E vs sector norm), earnings quality (EPS growth direction), margin profile, and debt sustainability (D/E ratio). Flag any red flags explicitly.
Step 4 — Sentiment Integration: Interpret sentiment_score and sentiment_label in context of price action. Positive sentiment with falling price = distribution warning. Negative sentiment with rising price = potential squeeze.
Step 5 — Risk Overlay: Apply Sharpe ratio, Beta, VaR, Max Drawdown, and Calmar ratio to size conviction. High Beta + high drawdown = reduce position sizing regardless of technical signal.
Step 6 — Synthesis and Ranking: Combine weighted scores. Rank stocks by conviction. Generate trigger levels from actual supplied price data. Produce portfolio-level recommendation.

=== WEIGHTING DEFAULTS ===
Technical: 45% | Fundamental: 35% | Sentiment: 20%
Adjust dynamically per rules 8, 9, 10 above. Always note weight adjustments in final_reasoning.

=== DECISION LABELS (exactly one per stock) ===
STRONG_BUY | BUY | HOLD | REDUCE | SELL | AVOID

=== SCORING (0-100) ===
85-100: Strong conviction — overwhelming evidence alignment
70-84: Constructive — majority signals agree with manageable conflicts
50-69: Mixed — signals in conflict, hold or reduce exposure
30-49: Weak — negative weight of evidence, reduce
0-29: Highly unfavorable — capital preservation priority

=== CONFIDENCE LOGIC ===
Derive confidence from:
1. Data completeness: Full data = +25 pts base. Each missing critical field (P/E, RSI, sentiment) = -5 pts.
2. Signal agreement: All 3 pillars (tech, fund, sentiment) agree direction = +25 pts. 2 of 3 = +15 pts. Only 1 = +5 pts.
3. Trend clarity: Strong trend (price clearly above/below all SMAs) = +20 pts. Choppy = +5 pts.
4. Contradiction absence: No major conflicts = +15 pts. Minor = +8 pts. Major = 0 pts.
5. Backtest validation: Strategy win_rate > 60% = +15 pts. 50-60% = +8 pts. Below 50% = 0 pts.
Max confidence = 100. Minimum = 10.

=== TRIGGER LOGIC (derive from supplied data) ===
For each stock provide:
- bullish_trigger: specific price level, indicator crossover, or fundamental event that would upgrade conviction
- bearish_trigger: specific price level, indicator breakdown, or deterioration that would downgrade
- invalidation: the specific price or metric breach that entirely negates the thesis

=== SPECIAL INSTRUCTION ROUTING ===
If user_question contains "which stock is best" or "top pick": Lead with the highest conviction stock in portfolio_actions.best_action_now. Justify with score and key differentiator.
If user_question contains "is this safe" or "downside": Emphasize bear_case, risk_notes, max_drawdown, VaR, and invalidation levels for all stocks.
If user_question contains "explain simply": Use plain language in final_reasoning without removing quantitative accuracy. Avoid jargon.
If user_question contains "what if market falls": In portfolio_actions, explicitly rank which positions break first based on Beta and Max Drawdown, and at what price levels.
If user_question contains "what changed": Note any directional change in RSI, MACD histogram, or sentiment from prior signals if detectable in the data trend.

=== STYLE RULES ===
- final_reasoning must read as a real analyst note — dense, evidence-cited, decisive.
- bull_case and bear_case must each have exactly 2 items, each grounded in supplied data.
- key_levels must use actual prices derived from SMA values, 52w_high, 52w_low, or current_price ± volatility bands.
- ai_disclaimer must be one professional sentence, not promotional.
- Never use filler phrases like "mixed picture", "various factors", or "market conditions".

=== OUTPUT SCHEMA (return ONLY this JSON, no other text) ===
{{
  "portfolio_summary": {{
    "market_regime": "",
    "overall_bias": "",
    "top_opportunity": "",
    "biggest_risk": "",
    "one_line_thesis": "",
    "weight_adjustment_applied": "",
    "confidence": 0
  }},
  "stocks": [
    {{
      "ticker": "",
      "score": 0,
      "decision": "",
      "confidence": 0,
      "horizon": "short_term | medium_term | long_term",
      "weights_used": {{"technical": 0, "fundamental": 0, "sentiment": 0}},
      "technical_view": "",
      "fundamental_view": "",
      "sentiment_view": "",
      "risk_view": "",
      "bull_case": ["", ""],
      "bear_case": ["", ""],
      "key_levels": {{
        "support": "",
        "resistance": "",
        "invalidation": ""
      }},
      "trigger_events": {{
        "bullish_trigger": "",
        "bearish_trigger": ""
      }},
      "position_sizing_note": "",
      "final_reasoning": "",
      "risk_notes": ""
    }}
  ],
  "ranked_watchlist": [
    {{
      "ticker": "",
      "rank": 1,
      "score": 0,
      "decision": "",
      "why_it_ranks_here": ""
    }}
  ],
  "portfolio_actions": {{
    "best_action_now": "",
    "avoid_now": "",
    "watch_for_next": "",
    "if_market_falls_first_to_break": "",
    "correlation_risk_note": ""
  }},
  "ai_disclaimer": ""
}}"""

QUANTCORE_HUMAN = """Analyze the following quantitative data and generate the QuantCore institutional JSON output.

PRIMARY TICKER UNDER ANALYSIS: {ticker}

=== USER INVESTMENT PROFILE ===
{user_prefs}

=== USER QUESTION / SPECIAL INSTRUCTION ===
{user_question}
(If empty, perform standard full analysis. If populated, apply Special Instruction Routing from your rules.)

=== STAGE 1: MARKET DATA (Price Action, 52-Week Range, Volume) ===
{market_data}

=== STAGE 2: TECHNICAL ANALYSIS (RSI, MACD, SMA 20/50/200, Volatility, Crossover Signals) ===
{technical_data}

=== STAGE 3: FUNDAMENTAL ANALYSIS (P/E, EPS, Revenue, Margins, D/E, Fundamental Score) ===
{fundamental_data}

=== STAGE 4: SENTIMENT ANALYSIS (VADER Score, LLM Label, News Headlines, Sources Count) ===
{sentiment_data}

=== STAGE 5: RISK ASSESSMENT (VaR, Beta, Sharpe, Calmar, Max Drawdown, Risk Grade) ===
{risk_data}

=== STAGE 6: BACKTEST RESULTS (SMA 20/50 Crossover Strategy, Win Rate, ROI, Drawdown) ===
{backtest_data}

INSTRUCTIONS:
1. Execute the 6-step analysis framework in order.
2. Apply dynamic weight adjustment rules if conditions are met — state applied weights explicitly.
3. Derive all key_levels from the actual supplied price data (current_price, sma20, sma50, sma200, 52w_high, 52w_low).
4. Derive confidence using the 5-factor formula from your system rules.
5. Return ONLY the JSON object. No markdown fences. No explanation outside the JSON."""


def _build_synthesis_chain(model: str = PRIMARY_MODEL):
    llm = ChatGroq(
        model=model,
        api_key=GROQ_API_KEY,
        temperature=0.05,
    )
    prompt = ChatPromptTemplate.from_messages([
        ("system", QUANTCORE_SYSTEM),
        ("human", QUANTCORE_HUMAN),
    ])
    return prompt | llm | JsonOutputParser()


# =============================================================================
#  MAIN PIPELINE — StockAnalysisPipeline
# =============================================================================

class StockAnalysisPipeline:
    """
    Orchestrates the 7-stage sequential QuantCore analysis pipeline.
    Usage:
        pipeline = StockAnalysisPipeline()
        result = pipeline.run(ticker="AAPL", user_prefs={...}, db=db)
    """

    def __init__(self):
        self.sentiment_chain = _build_sentiment_chain()
        self.synthesis_chain = _build_synthesis_chain()
        logger.info("StockAnalysisPipeline initialized with QuantCore decision engine v2.")

    def run(self, ticker: str, user_prefs: dict, db=None, user_question: str = "") -> dict:
        ticker = ticker.upper()
        pipeline_log = {}
        logger.info(f"[QuantCore] Starting 7-stage analysis for {ticker}")

        stage1 = self._stage1_market_data(ticker, db)
        pipeline_log["market_data"] = stage1
        if stage1.get("status") == "error":
            return {"error": f"Stage 1 failed: {stage1['message']}"}
        df = stage1["_dataframe"]

        stage2 = self._stage2_technical(df)
        pipeline_log["technical"] = stage2

        stage3 = self._stage3_fundamental(ticker)
        pipeline_log["fundamental"] = stage3

        stage4 = self._stage4_sentiment(ticker, db)
        pipeline_log["sentiment"] = stage4

        stage5 = self._stage5_risk(df)
        pipeline_log["risk"] = stage5

        stage6 = self._stage6_backtest(df, ticker)
        pipeline_log["backtest"] = stage6

        logger.info(f"[QuantCore] Running synthesis for {ticker}")
        quantcore_output = self._stage7_quantcore(
            ticker=ticker, user_prefs=user_prefs,
            stage1=stage1, stage2=stage2, stage3=stage3,
            stage4=stage4, stage5=stage5, stage6=stage6,
            user_question=user_question,
        )

        rec_data = self._extract_recommendation(quantcore_output, stage2, stage3, stage4, stage5)
        logger.info(f"[QuantCore] {ticker} → {rec_data['action']} ({rec_data['confidence']}%)")

        return {
            "ticker": ticker,
            "pipeline_steps": pipeline_log,
            "quantcore_output": quantcore_output,
            "final_report": self._build_report_text(quantcore_output, ticker),
            "recommendation": rec_data["action"],
            "confidence_score": rec_data["confidence"],
            "score_breakdown": rec_data["breakdown"],
            "risk_grade": stage5.get("risk_grade", "N/A"),
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

    # ─── Stage Implementations ────────────────────────────────────────────────

    def _stage1_market_data(self, ticker: str, db) -> dict:
        try:
            df = fetch_stock_data(ticker, period="1y", db=db)
            if df is None or df.empty:
                return {"status": "error", "message": "No market data found."}
            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) > 1 else latest
            chg = ((float(latest["Close"]) - float(prev["Close"])) / float(prev["Close"])) * 100
            return {
                "status": "ok", "ticker": ticker,
                "current_price": round(float(latest["Close"]), 2),
                "previous_close": round(float(prev["Close"]), 2),
                "price_change_pct": round(chg, 2),
                "52w_high": round(float(df["High"].max()), 2),
                "52w_low": round(float(df["Low"].min()), 2),
                "avg_volume_30d": int(df["Volume"].tail(30).mean()),
                "data_points": len(df), "period": "1 Year",
                "_dataframe": df,
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _stage2_technical(self, df) -> dict:
        try:
            tech_df = calculate_technical_indicators(df)
            summary = generate_technical_summary(tech_df)
            summary["status"] = "ok"
            return summary
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _stage3_fundamental(self, ticker: str) -> dict:
        try:
            result = evaluate_fundamentals(ticker)
            if result:
                result["status"] = "ok"
                return result
            return {"status": "error", "message": "No fundamental data available."}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _stage4_sentiment(self, ticker: str, db) -> dict:
        try:
            headlines_list = fetch_news_headlines(ticker)
            if not headlines_list:
                return {"status": "no_data", "sentiment_score": 0.0, "sentiment_label": "Neutral",
                        "reasoning": "No news headlines found.", "vader_score": 0.0, "sources_count": 0}

            vader_score = score_sentiment_with_vader(headlines_list)
            headlines_text = "\n".join([f"• {h}" for h in headlines_list])
            llm_result = invoke_with_retry(
                self.sentiment_chain,
                {"ticker": ticker, "headlines": headlines_text},
            )

            return {
                "status": "ok",
                "sentiment_score": llm_result.get("sentiment_score", vader_score),
                "sentiment_label": llm_result.get("sentiment_label", "Neutral"),
                "reasoning": llm_result.get("reasoning", ""),
                "vader_score": round(vader_score, 3),
                "sources_count": len(headlines_list),
                "headlines_analyzed": headlines_list[:5],
            }
        except Exception as e:
            logger.error(f"Stage 4 error: {e}")
            try:
                headlines_list = fetch_news_headlines(ticker)
                vader_score = score_sentiment_with_vader(headlines_list) if headlines_list else 0.0
                label = "Positive" if vader_score > 0.15 else "Negative" if vader_score < -0.15 else "Neutral"
                return {"status": "vader_fallback", "sentiment_score": round(vader_score, 3),
                        "sentiment_label": label, "reasoning": "VADER fallback used.",
                        "vader_score": round(vader_score, 3),
                        "sources_count": len(headlines_list) if headlines_list else 0}
            except Exception as e2:
                return {"status": "error", "sentiment_score": 0.0, "sentiment_label": "Neutral",
                        "reasoning": str(e2), "vader_score": 0.0, "sources_count": 0}

    def _stage5_risk(self, df) -> dict:
        try:
            result = calculate_risk_metrics(df)
            result["status"] = "ok"
            return result
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _stage6_backtest(self, df, ticker) -> dict:
        try:
            result = run_institutional_backtest(df, ticker, short_window=20, long_window=50)
            result["status"] = "ok"
            result["strategy"] = "SMA 20/50 Crossover"
            return {k: v for k, v in result.items() if k != "equity_curve"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _stage7_quantcore(self, ticker, user_prefs, stage1, stage2, stage3, stage4, stage5, stage6, user_question: str = "") -> dict:
        payload = {
            "ticker": ticker,
            "user_prefs": json.dumps(user_prefs, indent=2),
            "user_question": user_question or "Standard full analysis.",
            "market_data": json.dumps({k: v for k, v in stage1.items() if k != "_dataframe"}, indent=2, default=str),
            "technical_data": json.dumps(stage2, indent=2, default=str),
            "fundamental_data": json.dumps(stage3, indent=2, default=str),
            "sentiment_data": json.dumps(stage4, indent=2, default=str),
            "risk_data": json.dumps(stage5, indent=2, default=str),
            "backtest_data": json.dumps(stage6, indent=2, default=str),
        }
        try:
            # Attempt with primary model (Groq) with retry
            return invoke_with_retry(self.synthesis_chain, payload, max_retries=3, base_delay=5.0)
        except Exception as primary_err:
            logger.warning(f"[QuantCore] Primary model failed ({PRIMARY_MODEL}): {primary_err}. Trying fallback model {FALLBACK_MODEL}...")
            try:
                # Build a fresh chain on fallback model and retry once
                fallback_chain = _build_synthesis_chain(model=FALLBACK_MODEL)
                return invoke_with_retry(fallback_chain, payload, max_retries=2, base_delay=3.0)
            except Exception as e:
                logger.error(f"Stage 7 QuantCore error (all models exhausted): {e}")
            return {
                "error": str(e),
                "portfolio_summary": {
                    "market_regime": "Unknown", "overall_bias": "Neutral",
                    "top_opportunity": ticker, "biggest_risk": "Synthesis failed",
                    "one_line_thesis": "Analysis incomplete.", "confidence": 0
                },
                "stocks": [], "ranked_watchlist": [],
                "portfolio_actions": {
                    "best_action_now": "Retry analysis", "avoid_now": "All positions",
                    "watch_for_next": ticker
                },
                "ai_disclaimer": "Synthesis failed. Do not use for investment decisions."
            }

    def _build_report_text(self, quantcore_output: dict, ticker: str) -> str:
        """Builds a dense institutional markdown report from QuantCore JSON."""
        try:
            stocks = quantcore_output.get("stocks", [])
            stock = next((s for s in stocks if s.get("ticker") == ticker), stocks[0] if stocks else {})
            summary = quantcore_output.get("portfolio_summary", {})
            actions = quantcore_output.get("portfolio_actions", {})
            levels = stock.get("key_levels", {})
            triggers = stock.get("trigger_events", {})
            weights = stock.get("weights_used", {})
            bull = stock.get("bull_case", [])
            bear = stock.get("bear_case", [])
            watchlist = quantcore_output.get("ranked_watchlist", [])

            lines = [
                f"## QuantCore Institutional Research — {ticker}",
                f"\n**Market Regime:** {summary.get('market_regime', 'N/A')} | **Overall Bias:** {summary.get('overall_bias', 'N/A')}",
                f"\n**One-Line Thesis:** {summary.get('one_line_thesis', 'N/A')}",
                f"\n**Weight Adjustment:** {summary.get('weight_adjustment_applied', 'Default 45/35/20')}",
                f"\n---\n",
                f"### Decision: {stock.get('decision', 'N/A')} | Score: {stock.get('score', 0)}/100 | Confidence: {stock.get('confidence', 0)}% | Horizon: {stock.get('horizon', 'N/A')}",
                f"\n**Weights Applied:** Tech {weights.get('technical', 45)}% / Fund {weights.get('fundamental', 35)}% / Sent {weights.get('sentiment', 20)}%",
                f"\n**Technical View:** {stock.get('technical_view', 'N/A')}",
                f"\n**Fundamental View:** {stock.get('fundamental_view', 'N/A')}",
                f"\n**Sentiment View:** {stock.get('sentiment_view', 'N/A')}",
                f"\n**Risk View:** {stock.get('risk_view', 'N/A')}",
                f"\n**Position Sizing:** {stock.get('position_sizing_note', 'N/A')}",
                f"\n**Final Reasoning:** {stock.get('final_reasoning', 'N/A')}",
                f"\n**Risk Notes:** {stock.get('risk_notes', 'N/A')}",
                f"\n### Bull Case",
                *[f"- {b}" for b in bull],
                f"\n### Bear Case",
                *[f"- {b}" for b in bear],
                f"\n### Key Levels",
                f"- **Support:** {levels.get('support', 'N/A')}",
                f"- **Resistance:** {levels.get('resistance', 'N/A')}",
                f"- **Invalidation:** {levels.get('invalidation', 'N/A')}",
                f"\n### Trigger Events",
                f"- **Bullish Trigger:** {triggers.get('bullish_trigger', 'N/A')}",
                f"- **Bearish Trigger:** {triggers.get('bearish_trigger', 'N/A')}",
                f"\n### Portfolio Actions",
                f"- **Best Action Now:** {actions.get('best_action_now', 'N/A')}",
                f"- **Avoid Now:** {actions.get('avoid_now', 'N/A')}",
                f"- **Watch Next:** {actions.get('watch_for_next', 'N/A')}",
                f"- **First to Break in Downturn:** {actions.get('if_market_falls_first_to_break', 'N/A')}",
                f"- **Correlation Risk:** {actions.get('correlation_risk_note', 'N/A')}",
            ]

            if watchlist:
                lines.append(f"\n### Ranked Watchlist")
                for item in watchlist:
                    lines.append(f"- **#{item.get('rank')} {item.get('ticker')}** ({item.get('decision','N/A')}, {item.get('score', 0)}/100): {item.get('why_it_ranks_here', '')}")

            lines.append(f"\n*{quantcore_output.get('ai_disclaimer', '')}*")
            return "\n".join(lines)
        except Exception:
            return f"## QuantCore Analysis Complete — {ticker}\n\nView quantcore_output for full structured data."

    def _extract_recommendation(self, quantcore_output: dict, tech, fund, sent, risk) -> dict:
        """Extracts recommendation from QuantCore output, with algorithmic fallback."""
        DECISION_MAP = {"STRONG_BUY": "BUY", "BUY": "BUY", "HOLD": "HOLD",
                        "REDUCE": "SELL", "SELL": "SELL", "AVOID": "SELL"}
        try:
            stocks = quantcore_output.get("stocks", [])
            if stocks:
                stock = stocks[0]
                action = DECISION_MAP.get(stock.get("decision", "HOLD"), "HOLD")
                confidence = float(stock.get("confidence", 50))

                tech_score = float(tech.get("tech_score", 50))
                fund_score = float(fund.get("fundamental_score", 50))
                sent_pct = ((float(sent.get("sentiment_score", 0.0)) + 1) / 2) * 100
                risk_score = {"A": 90, "B": 75, "C": 55, "D": 35, "F": 15}.get(risk.get("risk_grade", "C"), 50)

                return {
                    "action": action, "confidence": confidence,
                    "breakdown": {
                        "technical": round(tech_score, 1),
                        "fundamental": round(fund_score, 1),
                        "sentiment": round(sent_pct, 1),
                        "risk": round(risk_score, 1),
                    }
                }
        except Exception as e:
            logger.warning(f"QuantCore extraction fallback triggered: {e}")

        # Pure algorithmic fallback
        tech_score = float(tech.get("tech_score", 50))
        fund_score = float(fund.get("fundamental_score", 50))
        sent_pct = ((float(sent.get("sentiment_score", 0.0)) + 1) / 2) * 100
        risk_score = {"A": 90, "B": 75, "C": 55, "D": 35, "F": 15}.get(risk.get("risk_grade", "C"), 50)
        final_score = (tech_score * 0.4) + (fund_score * 0.3) + (sent_pct * 0.2) + (risk_score * 0.1)
        action = "BUY" if final_score >= 62 else "SELL" if final_score <= 42 else "HOLD"

        return {
            "action": action, "confidence": round(final_score, 1),
            "breakdown": {
                "technical": round(tech_score, 1),
                "fundamental": round(fund_score, 1),
                "sentiment": round(sent_pct, 1),
                "risk": round(risk_score, 1),
            }
        }
