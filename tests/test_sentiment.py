from unittest.mock import MagicMock, patch

from services.sentiment import analyze_sentiment, fetch_news_headlines, score_sentiment_with_vader


def test_score_sentiment_with_vader():
    positive_headlines = [
        "Company reports record-breaking quarterly revenue and unprecedented profits",
        "Stock surges after groundbreaking innovation announcement",
    ]
    score = score_sentiment_with_vader(positive_headlines)
    assert score > 0.3

    negative_headlines = [
        "Company faces catastrophic loss and massive regulatory fraud investigation",
        "Disastrous decline leads to severe bankruptcy concerns",
    ]
    neg_score = score_sentiment_with_vader(negative_headlines)
    assert neg_score < -0.3

    assert score_sentiment_with_vader([]) == 0.0


@patch("services.sentiment.yf.Search")
def test_fetch_news_headlines_yf_search(mock_search):
    mock_instance = MagicMock()
    mock_instance.news = [
        {"title": "Headline 1"},
        {"title": "Headline 2"},
        {"title": ""},
    ]
    mock_search.return_value = mock_instance

    headlines = fetch_news_headlines("AAPL")
    assert headlines == ["Headline 1", "Headline 2"]


@patch("services.sentiment.yf.Search", side_effect=Exception("API Error"))
@patch("services.sentiment.requests.get")
def test_fetch_news_headlines_rss_fallback(mock_get, mock_search):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
        <channel>
            <item><title>RSS Headline 1</title></item>
            <item><title>RSS Headline 2</title></item>
        </channel>
    </rss>"""
    mock_get.return_value = mock_response

    headlines = fetch_news_headlines("AAPL")
    assert headlines == ["RSS Headline 1", "RSS Headline 2"]


@patch("services.sentiment.fetch_news_headlines")
def test_analyze_sentiment_deterministic(mock_fetch):
    mock_fetch.return_value = [
        "Strong rally observed in institutional equity portfolios",
        "Record breaking performance delivers outstanding growth",
    ]
    result = analyze_sentiment("AAPL")
    assert result is not None
    assert result["sentiment_score"] > 0
    assert result["sentiment_label"] in ["Positive", "Neutral"]
    assert "Strong rally" in result["summary_text"]
