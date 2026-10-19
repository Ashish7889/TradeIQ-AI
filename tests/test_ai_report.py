import json

from langchain_core.output_parsers import JsonOutputParser

from services.ai_report import ReportOutput, _parse_report_json


def test_parse_report_json_valid():
    parser = JsonOutputParser(pydantic_object=ReportOutput)
    valid_data = {
        "report": "## Executive Summary\nAmazon and Microsoft show strong momentum.",
        "final_score": 78,
        "score_breakdown": {"technical": 80, "fundamental": 75, "sentiment": 80, "risk": 70},
        "recommendation": "BUY",
        "confidence_score": 85,
        "strategy_accuracy": 68.5,
        "decision_triggers": ["RSI below 40"]
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
        "decision_triggers": []
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
        "MSFT": {"Technicals": {}, "Fundamentals": {}}
    }
    tickers = list(stock_analysis_data.keys())
    assert tickers == ["AMZN", "MSFT"]
