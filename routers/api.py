from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import get_db
from models import Watchlist, UserPreference, User
import schemas
from security import get_current_user

from services.stock_data import fetch_stock_data
from services.technical import calculate_technical_indicators, generate_technical_summary
from services.sentiment import analyze_sentiment
from services.fundamental import evaluate_fundamentals
from services.recommendation import generate_recommendation
from services.quant_backtest import run_institutional_backtest
from services.langchain_agent import StockAnalysisPipeline

router = APIRouter()

# Initialize the LangChain pipeline once at module load (reused across requests)
_pipeline = StockAnalysisPipeline()

@router.get("/search")
def search_stock(ticker: str, db: Session = Depends(get_db)):
    """Validates if ticker exists and fetches basic info."""
    df = fetch_stock_data(ticker, period="1d", db=db)
    if df is None:
        raise HTTPException(status_code=404, detail="Ticker not found or data unavailable")
    return {"message": "Success", "ticker": ticker.upper()}

@router.get("/stock/{ticker}/price")
def get_price_history(ticker: str, period: str = "1y", db: Session = Depends(get_db)):
    df = fetch_stock_data(ticker, period=period, db=db)
    if df is None:
        raise HTTPException(status_code=404, detail="Ticker not found")
        
    # Safely convert 'Date' to string format for JSON serialization
    import pandas as pd
    try:
        df['Date'] = pd.to_datetime(df['Date'], utc=True).dt.strftime('%Y-%m-%d')
    except Exception:
        df['Date'] = df['Date'].astype(str).str.split(' ').str[0]
        
    # Drop NaNs just in case
    df = df.dropna(subset=['Open', 'High', 'Low', 'Close'])
    
    records = df[['Date', 'Open', 'High', 'Low', 'Close', 'Volume']].to_dict(orient="records")
    return {"ticker": ticker.upper(), "data": records}

@router.get("/stock/{ticker}/technical", response_model=schemas.TechSummary)
def get_technical(ticker: str, db: Session = Depends(get_db)):
    df = fetch_stock_data(ticker, period="1y", db=db)
    if df is None:
        raise HTTPException(status_code=404, detail="Ticker not found")
        
    tech_df = calculate_technical_indicators(df)
    summary = generate_technical_summary(tech_df)
    return summary

@router.get("/stock/{ticker}/sentiment", response_model=schemas.SentimentSummary)
def get_sentiment(ticker: str, db: Session = Depends(get_db)):
    result = analyze_sentiment(ticker, db=db)
    if not result:
        raise HTTPException(status_code=404, detail="No sentiment data available")
    return result

@router.get("/stock/{ticker}/fundamental", response_model=schemas.FundSummary)
def get_fundamental(ticker: str):
    result = evaluate_fundamentals(ticker)
    if not result:
        raise HTTPException(status_code=404, detail="No fundamental data available")
    return result

@router.get("/stock/{ticker}/recommendation", response_model=schemas.RecommendationOut)
def get_recommendation(ticker: str, db: Session = Depends(get_db)):
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
def remove_from_watchlist(ticker: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
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
def get_backtest(ticker: str, db: Session = Depends(get_db)):
    df = fetch_stock_data(ticker, period="1y", db=db)
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail="Ticker not found")
    
    # Run historical simulation
    results = run_institutional_backtest(df, ticker)
    return results

@router.post("/report/generate")
def generate_report(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from services.ai_report import generate_user_report
    result = generate_user_report(db, current_user)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.get("/stock/{ticker}/langchain-analysis", response_model=schemas.AnalysisReportOut)
def run_langchain_pipeline(
    ticker: str,
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

    return result

