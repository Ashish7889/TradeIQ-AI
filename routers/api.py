from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

import schemas
from database import get_db
from dependencies import valid_ticker
from limiter import limiter
from models import User, UserPreference, Watchlist
from security import get_current_user
from services.fundamental import evaluate_fundamentals
from services.langchain_agent import StockAnalysisPipeline
from services.quant_backtest import run_institutional_backtest
from services.recommendation import generate_recommendation
from services.sentiment import analyze_sentiment
from services.stock_data import fetch_stock_data
from services.technical import (
    calculate_technical_indicators,
    generate_technical_summary,
)

router = APIRouter()

# Initialize the LangChain pipeline once at module load (reused across requests)
_pipeline = StockAnalysisPipeline()

@router.get("/search")
def search_stock(ticker: str = Depends(valid_ticker), db: Session = Depends(get_db)):
    """Validates if ticker exists and fetches basic info."""
    df = fetch_stock_data(ticker, period="1d", db=db)
    if df is None:
        raise HTTPException(status_code=404, detail="Ticker not found or data unavailable")
    return {"message": "Success", "ticker": ticker.upper()}

@router.get("/stock/{ticker}/price")
def get_price_history(ticker: str = Depends(valid_ticker), period: str = "1y", db: Session = Depends(get_db)):
    df = fetch_stock_data(ticker, period=period, db=db)
    if df is None:
        raise HTTPException(status_code=404, detail="Ticker not found")
        
    # Safely convert 'Date' to string format for JSON serialization
    import pandas as pd
    try:
        df['Date'] = pd.to_datetime(df['Date'], utc=True).dt.strftime('%Y-%m-%d')
    except (ValueError, TypeError, KeyError):
        df['Date'] = df['Date'].astype(str).str.split(' ').str[0]
        
    # Drop NaNs just in case
    df = df.dropna(subset=['Open', 'High', 'Low', 'Close'])
    
    records = df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']].to_dict(orient="records")
    return {"ticker": ticker.upper(), "data": records}

@router.get("/stock/{ticker}/technical", response_model=schemas.TechSummary)
def get_technical(ticker: str = Depends(valid_ticker), db: Session = Depends(get_db)):
    df = fetch_stock_data(ticker, period="1y", db=db)
    if df is None:
        raise HTTPException(status_code=404, detail="Ticker not found")
        
    tech_df = calculate_technical_indicators(df)
    summary = generate_technical_summary(tech_df)
    return summary

@router.get("/stock/{ticker}/sentiment", response_model=schemas.SentimentSummary)
@limiter.limit("20/minute")
def get_sentiment(request: Request, ticker: str = Depends(valid_ticker), db: Session = Depends(get_db)):
    result = analyze_sentiment(ticker, db=db)
    if not result:
        raise HTTPException(status_code=404, detail="No sentiment data available")
    return result

@router.get("/stock/{ticker}/fundamental", response_model=schemas.FundSummary)
def get_fundamental(ticker: str = Depends(valid_ticker)):
    result = evaluate_fundamentals(ticker)
    if not result:
        raise HTTPException(status_code=404, detail="No fundamental data available")
    return result

@router.get("/stock/{ticker}/recommendation", response_model=schemas.RecommendationOut)
@limiter.limit("20/minute")
def get_recommendation(
    request: Request,
    ticker: str = Depends(valid_ticker),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    df = fetch_stock_data(ticker, period="1y", db=db)
    if df is None:
        raise HTTPException(status_code=404, detail="Ticker not found")
        
    tech_df = calculate_technical_indicators(df)
    tech_summary = generate_technical_summary(tech_df)
    
    sentiment_summary = analyze_sentiment(ticker, db=db)
    fund_summary = evaluate_fundamentals(ticker)
    
    rec = generate_recommendation(tech_summary, sentiment_summary, fund_summary)
    return rec

@router.post("/watchlist/add")
def add_to_watchlist(item: schemas.WatchlistAdd, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    ticker = item.ticker.upper()
    existing = db.query(Watchlist).filter(Watchlist.ticker == ticker, Watchlist.user_id == current_user.id).first()
    if existing:
        return {"message": "Already in watchlist"}
    new_item = Watchlist(ticker=ticker, user_id=current_user.id)
    db.add(new_item)
    db.commit()
    return {"message": f"Added {ticker} to watchlist"}

@router.delete("/watchlist/{ticker}")
def remove_from_watchlist(ticker: str = Depends(valid_ticker), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    ticker = ticker.upper()
    item = db.query(Watchlist).filter(Watchlist.ticker == ticker, Watchlist.user_id == current_user.id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Stock not found in watchlist")
    db.delete(item)
    db.commit()
    return {"message": f"Removed {ticker} from watchlist"}

@router.delete("/watchlist")
def clear_watchlist(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db.query(Watchlist).filter(Watchlist.user_id == current_user.id).delete()
    db.commit()
    return {"message": "Watchlist cleared"}

@router.get("/watchlist")
def get_watchlist(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    items = db.query(Watchlist).filter(Watchlist.user_id == current_user.id).all()
    # Let's also fetch latest prices
    result = []
    for item in items:
        df = fetch_stock_data(item.ticker, period="1d", db=db)
        if df is not None and not df.empty:
             val = float(df.iloc[-1]['Close'])
             result.append({"ticker": item.ticker, "price": round(val, 2)})
        else:
             result.append({"ticker": item.ticker, "price": None})
             
    return result

@router.get("/preferences", response_model=schemas.PreferenceOut)
def get_preferences(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    prefs = db.query(UserPreference).filter(UserPreference.user_id == current_user.id).first()
    if not prefs:
        raise HTTPException(status_code=404, detail="Preferences not found")
    return prefs

@router.put("/preferences", response_model=schemas.PreferenceOut)
def update_preferences(prefs_in: schemas.PreferenceUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    prefs = db.query(UserPreference).filter(UserPreference.user_id == current_user.id).first()
    if not prefs:
        prefs = UserPreference(user_id=current_user.id)
        db.add(prefs)
    
    prefs.risk_level = prefs_in.risk_level
    prefs.investment_type = prefs_in.investment_type
    prefs.focus_type = prefs_in.focus_type
    prefs.budget_range = prefs_in.budget_range
    prefs.expected_return = prefs_in.expected_return
    
    db.commit()
    db.refresh(prefs)
    return prefs
@router.get("/stock/{ticker}/backtest")
def get_backtest(ticker: str = Depends(valid_ticker), db: Session = Depends(get_db)):
    df = fetch_stock_data(ticker, period="1y", db=db)
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail="Ticker not found")
    
    # Run historical simulation
    results = run_institutional_backtest(df, ticker)
    return results

@router.post("/report/generate")
@limiter.limit("20/minute")
def generate_report(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from services.ai_report import generate_user_report
    result = generate_user_report(db, current_user)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/stock/{ticker}/langchain-analysis", response_model=schemas.AnalysisReportOut)
@limiter.limit("20/minute")
def run_langchain_pipeline(
    request: Request,
    ticker: str = Depends(valid_ticker),
    user_question: str = "",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Runs the 'Top-Tier' Quantitative Research Pipeline.
    
    1. Deterministic Analysis (Tech, Fund, Risk, Sent)
    2. Decision Engine (Weighted Score + Confidence)
    3. Groq Synthesis (Institutional Report Formatting)
    """
    # Load user preferences for personalized synthesis
    prefs = db.query(UserPreference).filter(UserPreference.user_id == current_user.id).first()
    user_prefs = {
        "risk_level": prefs.risk_level if prefs else "Medium",
        "investment_type": prefs.investment_type if prefs else "Long-term",
        "focus_type": prefs.focus_type if prefs else "Technical",
        "budget_range": prefs.budget_range if prefs else "Not specified",
        "expected_return": prefs.expected_return if prefs else "Not specified",
    }

    result = _pipeline.run(ticker=ticker, user_prefs=user_prefs, db=db, user_question=user_question)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    stocks = result.get("quantcore_output", {}).get("stocks", [])
    stock = next((s for s in stocks if s.get("ticker") == ticker.upper()), stocks[0] if stocks else {})
    final_score = float(stock.get("score", stock.get("confidence", result.get("confidence_score", 50.0))))

    pipeline_steps = result.get("pipeline_steps", {})
    if isinstance(pipeline_steps, dict):
        market_data = pipeline_steps.get("market_data", {})
        if isinstance(market_data, dict) and "_dataframe" in market_data:
            pipeline_steps["market_data"] = {k: v for k, v in market_data.items() if k != "_dataframe"}

    result["final_score"] = final_score
    result["report"] = result.get("final_report", "")
    result["full_data"] = pipeline_steps

    return result

