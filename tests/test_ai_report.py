import json
from unittest.mock import MagicMock

from langchain_core.output_parsers import JsonOutputParser

from services.ai_report import (
    ReportOutput,
    _parse_report_json,
    compute_profile_quant_decisions,
    generate_user_report,
)


def test_parse_report_json_valid():
    parser = JsonOutputParser(pydantic_object=ReportOutput)
    valid_data = {
        "report": "## Executive Summary\nAmazon and Microsoft show strong momentum.",
        "final_score": 78,
        "score_breakdown": {"technical": 80, "fundamental": 75, "sentiment": 80, "risk": 70},
        "recommendation": "BUY",
        "confidence_score": 85,
        "strategy_accuracy": 68.5,
        "decision_triggers": ["RSI below 40"],
    }
    raw = json.dumps(valid_data)
    parsed = _parse_report_json(raw, parser)
    assert parsed["final_score"] == 78
    assert parsed["recommendation"] == "BUY"
    assert parsed["confidence_score"] == 85


def test_parse_report_json_fenced_markdown():
    parser = JsonOutputParser(pydantic_object=ReportOutput)
    valid_data = {
        "report": "## Markdown in json",
        "final_score": 60,
        "score_breakdown": {},
        "recommendation": "HOLD",
        "confidence_score": 50,
        "strategy_accuracy": 55.0,
        "decision_triggers": [],
    }
    raw = f"```json\n{json.dumps(valid_data)}\n```"
    parsed = _parse_report_json(raw, parser)
    assert parsed["recommendation"] == "HOLD"
    assert parsed["final_score"] == 60


def test_parse_report_json_unstructured_fallback():
    parser = JsonOutputParser(pydantic_object=ReportOutput)
    raw = "Here is the memo:\n### Tactical View\nWe recommend a strong **BUY** based on tech indicators."
    parsed = _parse_report_json(raw, parser)
    assert parsed["recommendation"] == "BUY"
    assert "Tactical View" in parsed["report"]
    assert parsed["final_score"] == 50


def test_ticker_extraction_from_dict():
    stock_analysis_data = {
        "AMZN": {"Technicals": {}, "Fundamentals": {}},
        "MSFT": {"Technicals": {}, "Fundamentals": {}},
    }
    tickers = list(stock_analysis_data.keys())
    assert tickers == ["AMZN", "MSFT"]


def test_profile_quant_decisions_differ():
    sample_data = {
        "AAPL": {
            "Technicals": {
                "tech_score": 70.0,
                "rsi": 55.0,
                "macd": 1.2,
                "volatility": 0.28,
                "numerical_evidence": ["Price is trading 2.5% above 20-day SMA.", "Above 200-day SMA by 8.0%."],
            },
            "Fundamentals": {
                "available": True,
                "fundamental_score": 80.0,
                "metrics": {"pe_ratio": 28.0},
            },
            "Sentiment": {
                "sentiment_score": 0.4,
            },
            "Backtest": {
                "accuracy": 65.0,
                "max_drawdown": 0.22,
            },
        }
    }

    # Profile A: Aggressive, Short-term, Technical
    profile_a = {
        "risk_level": "High",
        "investment_type": "Short-term",
        "focus_type": "Technical",
        "budget_range": "$10,000",
        "expected_return": "25%",
    }
    dec_a = compute_profile_quant_decisions(sample_data, profile_a)

    # Profile B: Conservative, Long-term, Fundamental
    profile_b = {
        "risk_level": "Low",
        "investment_type": "Long-term",
        "focus_type": "Fundamental",
        "budget_range": "$100,000",
        "expected_return": "8%",
    }
    dec_b = compute_profile_quant_decisions(sample_data, profile_b)

    # Assert weights differ based on focus_type
    assert dec_a["weights"]["technical"] == 0.55
    assert dec_a["weights"]["fundamental"] == 0.15
    assert dec_a["weights"]["sentiment"] == 0.30

    assert dec_b["weights"]["technical"] == 0.20
    assert dec_b["weights"]["fundamental"] == 0.55
    assert dec_b["weights"]["sentiment"] == 0.25

    # Assert thresholds differ based on risk_level
    assert dec_a["buy_threshold"] == 55
    assert dec_a["sell_threshold"] == 35
    assert dec_b["buy_threshold"] == 75
    assert dec_b["sell_threshold"] == 45

    # Assert applied profile strings match specifications
    assert dec_a["applied_profile"] == "Aggressive · Short-term · Technical"
    assert dec_b["applied_profile"] == "Conservative · Long-term · Fundamental"

    # Conservative profile penalizes 22% drawdown (since > 15%), whereas Aggressive has no penalty
    assert dec_b["ticker_results"]["AAPL"]["penalty"] > 0
    assert dec_a["ticker_results"]["AAPL"]["penalty"] == 0


def test_fundamental_missing_notice():
    sample_data_no_fund = {
        "TSLA": {
            "Technicals": {"tech_score": 60.0},
            "Fundamentals": {"available": False, "fundamental_score": None},
            "Sentiment": {"sentiment_score": 0.0},
            "Backtest": {"max_drawdown": 0.10},
        }
    }
    profile_fund = {
        "risk_level": "Medium",
        "investment_type": "Long-term",
        "focus_type": "Fundamental",
    }
    dec = compute_profile_quant_decisions(sample_data_no_fund, profile_fund)
    assert dec["has_missing_fundamentals"] is True
    assert dec["fundamental_notice"] is not None
    assert "Fundamental focus is running without complete fundamental" in dec["fundamental_notice"]


def test_generate_user_report_prompt_with_mocked_llm(monkeypatch):
    # Mock user and preferences in DB
    mock_user = MagicMock()
    mock_user.id = 42

    mock_pref = MagicMock()
    mock_pref.risk_level = "High"
    mock_pref.investment_type = "Long-term"
    mock_pref.focus_type = "Fundamental"
    mock_pref.budget_range = "$50,000"
    mock_pref.expected_return = "20%"

    mock_watchlist_item = MagicMock()
    mock_watchlist_item.ticker = "AAPL"

    mock_db = MagicMock()
    # First query is for UserPreference, second is for Watchlist
    mock_db.query.return_value.filter.return_value.first.return_value = mock_pref
    mock_db.query.return_value.filter.return_value.all.return_value = [mock_watchlist_item]

    # Mock _process_single_ticker to avoid slow network calls
    def fake_process(ticker):
        return ticker, {
            "Technicals": {
                "tech_score": 75.0,
                "rsi": 50.0,
                "macd": 1.0,
                "volatility": 0.20,
                "numerical_evidence": ["Above 200-day SMA by 5.0%."],
            },
            "Fundamentals": {"available": True, "fundamental_score": 85.0, "metrics": {"pe_ratio": 25.0}},
            "Sentiment": {"sentiment_score": 0.5},
            "Backtest": {"accuracy": 70.0, "max_drawdown": 0.12},
        }

    monkeypatch.setattr("services.ai_report._process_single_ticker", fake_process)

    # Capture arguments passed to chain.invoke
    captured_invocations = []

    class FakeChain:
        def invoke(self, input_dict):
            captured_invocations.append(input_dict)
            fake_response = MagicMock()
            fake_response.content = json.dumps(
                {
                    "report": "## Executive Memorandum\nAAPL shows institutional strength.",
                    "final_score": 80,
                    "score_breakdown": {"technical": 75, "fundamental": 85, "sentiment": 75, "risk": 80},
                    "recommendation": "BUY",
                    "confidence_score": 88,
                    "strategy_accuracy": 70.0,
                    "decision_triggers": ["Breakdown below 200 SMA"],
                }
            )
            return fake_response

    class FakeParser:
        def get_format_instructions(self):
            return "json schema instructions"

    monkeypatch.setattr("services.ai_report._build_report_chain", lambda model: (FakeChain(), FakeParser()))

    result = generate_user_report(mock_db, mock_user)

    assert len(captured_invocations) == 1
    inv = captured_invocations[0]

    # Assert prompt contains the saved profile fields
    assert inv["risk_level"] == "High"
    assert inv["investment_type"] == "Long-term"
    assert inv["focus_type"] == "Fundamental"
    assert inv["budget_range"] == "$50,000"
    assert inv["expected_return"] == "20%"
    assert inv["applied_profile"] == "Aggressive · Long-term · Fundamental"
    assert "Fundamental 55%" in inv["weights_info"]

    # Assert deterministic result outputs
    assert result["applied_profile"] == "Aggressive · Long-term · Fundamental"
    assert result["recommendation"] == "BUY"
    assert result["weights"]["fundamental"] == 0.55
