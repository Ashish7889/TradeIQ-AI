# StockSense AI (TradeIQ)

StockSense AI (TradeIQ) is a stock research and analysis web application built as a portfolio project. It integrates market data retrieval, technical indicators, fundamental valuation metrics, statistical risk measures, and a rule-based backtest engine, using LangChain-orchestrated Groq Large Language Models (LLMs) to synthesize structured research memorandums.

---

## Architecture

```
                      ┌───────────────────────────────────────┐
                      │    Vanilla JS Web UI / Streamlit      │
                      └──────────────────┬────────────────────┘
                                         │ HTTP REST
                      ┌──────────────────▼────────────────────┐
                      │          FastAPI Backend              │
                      │  - SlowAPI Rate Limiting (5/m, 20/m)  │
                      │  - Ticker Regex Validation (422)      │
                      │  - JWT Auth (Bearer, 60m expiry)      │
                      │  - Process Time Logging Middleware    │
                      └───────┬──────────────────────┬────────┘
                              │                      │
             ┌────────────────▼─────────┐   ┌────────▼────────────────┐
             │   Quantitative Engines   │   │   LangChain AI Pipeline │
             │ - Technical(SMA,RSI,MACD)│   │ - Groq qwen/qwen3.8-27b │
             │ - Fundamental (P/E, EPS) │   │ - Fallback gpt-oss-20b  │
             │ - Risk (VaR 95%, Sharpe) │   │ - Structured Memo Output│
             │ - Backtest (RSI + SMA50) │   └─────────────────────────┘
             └────────────────┬─────────┘
                              │
                      ┌───────▼────────────────┐
                      │   SQLAlchemy & Cache   │
                      │ - In-Memory TTL Cache  │
                      │ - SQLite / Relational  │
                      │ - pbkdf2_sha256 Hashing│
                      └────────────────────────┘
```

- **API Layer**: FastAPI application using `pydantic-settings`, strict ticker input validation (`^[A-Z.\-]{1,10}$`), and `slowapi` rate limits (5/min on auth, 20/min on data routes). No CORS middleware is configured.
- **Quantitative Engine**: Pure deterministic calculations for annualized volatility, Sharpe ratio, beta vs S&P 500 (SPY), historical Value at Risk (VaR 95%), maximum drawdown, and a 1-year historical signal backtester (RSI + SMA50 cross). (A separate weighted score engine is provided in `services/recommendation.py`).
- **AI Synthesis**: LangChain pipeline querying Groq LLMs (`qwen/qwen3.8-27b` with `openai/gpt-oss-20b` fallback) with structured output parsing to generate research memorandums.
- **Storage & Security**: SQLAlchemy ORM with SQLite database. User passwords are encrypted using `pbkdf2_sha256` via `passlib`.

---

## Environment Variables

Copy `.env.example` to `.env` and configure your credentials:

| Variable | Description | Default |
|---|---|---|
| `SECRET_KEY` | Secret key used for signing JWT access tokens (min. 16 chars) | *None (Fails on startup if missing)* |
| `ALGORITHM` | Token signing algorithm | `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token expiration lifetime in minutes | `60` |
| `GROQ_API_KEY` | API Key from Groq Console for LLM inference | Required |
| `GROQ_MODEL` | Primary LLM model name | `qwen/qwen3.8-27b` |
| `GROQ_FALLBACK_MODEL` | Fallback model if primary encounters errors | `openai/gpt-oss-20b` |
| `DATABASE_URL` | SQLAlchemy database connection URI | `sqlite:///./data/stocksense.db` |

---

## Getting Started

### Local Setup

1. **Clone & Create Environment**:
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   # For running tests and dev tools:
   pip install -r requirements-dev.txt pytest ruff httpx pytest-cov
   ```

3. **Configure Environment**:
   ```bash
   cp .env.example .env
   # Set a strong SECRET_KEY (32+ chars) and your GROQ_API_KEY in .env
   ```

4. **Run Server**:
   ```bash
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```
   Open `http://localhost:8000` in your browser. Interactive OpenAPI documentation is available at `http://localhost:8000/docs`.

### Docker Setup

The project uses a single-stage `python:3.11-slim` container running as a non-root user:

1. **Build Container**:
   ```bash
   docker build -t stocksense-ai:latest .
   ```

2. **Run Container**:
   ```bash
   docker run -p 10000:10000 --env-file .env stocksense-ai:latest
   ```

---

## Running Tests

The test suite contains 49 automated unit and API integration tests covering technical indicators, fundamental evaluation and caching, risk metrics, backtesting, input validation, authentication, and user preferences:

```bash
# Run pytest with coverage
pytest --cov=. --cov-report=term-missing -v

# Run linter & formatter checks
ruff check .
ruff format --check .
```

---

## Known Limitations

- **yfinance Rate Limits**: Fundamental financial data is retrieved via `yfinance`. Upstream Yahoo Finance rate limiting can occasionally cause balance sheet or valuation metrics to be missing or delayed.
- **Free-Tier Cold Starts**: When hosted on free-tier services (such as Render), the backend instance spins down after periods of inactivity, resulting in cold-start delays on initial requests.
- **LLM Synthesis Variance**: While quantitative technical and risk calculations are deterministic, narrative explanations generated by the LLM can vary between executions.

---

## Disclaimer

**NOT FINANCIAL ADVICE**: StockSense AI is strictly an educational and software demonstration project. None of the reports, metrics, sentiment ratings, or model outputs constitute financial, investment, or trading advice. Past performance and algorithmic backtests do not guarantee future returns. Always conduct your own independent due diligence and consult a licensed financial professional before making investment decisions.

