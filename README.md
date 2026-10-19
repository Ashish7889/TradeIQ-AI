# StockSense AI 📈🤖

StockSense AI is an institutional-grade quantitative financial research terminal. It combines algorithmic technical indicators, fundamental valuation, statistical risk modeling, and backtesting with LangChain-orchestrated Groq Large Language Models (LLMs) to synthesize objective stock intelligence.

---

## 🏛️ Architecture

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
                      │  - APM Observability Middleware       │
                      └───────┬──────────────────────┬────────┘
                              │                      │
             ┌────────────────▼─────────┐   ┌────────▼────────────────┐
             │   Quantitative Engines   │   │   LangChain AI Pipeline │
             │ - Technical (RSI, MACD)  │   │ - Groq Llama-3.3-70b    │
             │ - Fundamental (P/E, EPS) │   │ - Fallback Llama-8b     │
             │ - Risk Engine(VaR, MaxDD)│   │ - Structured Analysis   │
             │ - Backtest (RSI + SMA50) │   └─────────────────────────┘
             └────────────────┬─────────┘
                              │
                      ┌───────▼────────────────┐
                      │   SQLAlchemy & Cache   │
                      │ - Thread-safe TTL Cache│
                      │ - SQLite / PostgreSQL  │
                      └────────────────────────┘
```

- **API Layer**: FastAPI application configured with `pydantic-settings`, strict ticker input validation (`^[A-Z.\-]{1,10}$`), and `slowapi` rate limits.
- **Quantitative Engine**: Pure deterministic calculations (no hallucinations) for volatility, Sharpe ratio, historical VaR (95%), peak-to-trough drawdown via log returns, and RSI/SMA signal backtesting.
- **AI Synthesis**: LangChain pipeline querying Groq LLMs with fallback resilience to generate structured investment memorandums.
- **Storage**: SQLAlchemy ORM with thread-safe market data caching (`cachetools` + `threading.Lock`).

---

## ⚙️ Environment Variables

Copy `.env.example` to `.env` and configure your credentials:

| Variable | Description | Default |
|---|---|---|
| `SECRET_KEY` | Secret key used for signing JWT access tokens | `stocksense-institution-secret-key-change-in-production` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token expiration lifetime in minutes | `60` |
| `GROQ_API_KEY` | API Key from Groq Console for LLM inference | Required |
| `GROQ_MODEL` | Primary LLM model name | `llama-3.3-70b-versatile` |
| `GROQ_FALLBACK_MODEL` | Fallback model if primary encounters rate limits | `llama-3.1-8b-instant` |
| `DATABASE_URL` | SQLAlchemy database connection URI | `sqlite:///./data/stocksense.db` |

---

## 🚀 Getting Started

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
   # Optional: install dev/dashboard tools (Streamlit, Plotly, Pytest, Ruff)
   pip install -r requirements-dev.txt pytest ruff httpx
   ```

3. **Configure Environment**:
   ```bash
   cp .env.example .env
   # Add your GROQ_API_KEY inside .env
   ```

4. **Run Server**:
   ```bash
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```
   Open your browser at `http://localhost:8000` to access the terminal interface, or `http://localhost:8000/docs` for interactive OpenAPI documentation.

### Docker Setup

1. **Build Container**:
   ```bash
   docker build -t stocksense-ai:latest .
   ```

2. **Run Container**:
   ```bash
   docker run -p 8000:8000 --env-file .env stocksense-ai:latest
   ```

---

## 🧪 Running Tests

The test suite contains unit tests covering technical indicators, fundamental evaluation, risk metrics, backtesting, ticker regex validation, and authentication flows with in-memory SQLite:

```bash
# Run pytest
pytest -v

# Run linter
ruff check .
```

---

## ⚠️ Disclaimer

**NOT FINANCIAL ADVICE**: StockSense AI is strictly an educational and quantitative research tool. None of the reports, metrics, sentiment ratings, or model outputs constitute financial, investment, or trading advice. Past performance and algorithmic backtests do not guarantee future returns. Always conduct your own independent due diligence and consult a licensed financial advisor before making investment decisions.
