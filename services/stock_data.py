import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from models import Stock
import logging
from cachetools import TTLCache

logger = logging.getLogger(__name__)

# Institutional-grade caching: 15 min TTL, max 200 items to prevent memory bloat
market_data_cache = TTLCache(maxsize=200, ttl=900)

def fetch_stock_data(ticker: str, period: str = "1y", db: Session = None):
    """
    Fetches historical OHLCV data for a ticker using yfinance.
    Saves/updates the stock in the database if db is provided.
    Returns the pandas DataFrame.
    """
    ticker = ticker.upper()
    cache_key = f"{ticker}_{period}"
    
    try:
        # Check cache first
        if cache_key in market_data_cache:
            logger.info(f"[Cache Hit] Market data for {cache_key}")
            df = market_data_cache[cache_key].copy()
        else:
            logger.info(f"[Cache Miss] Fetching data for {cache_key} from Yahoo Finance")
            stock = yf.Ticker(ticker)
            df = stock.history(period=period)
            
            if df.empty:
                logger.warning(f"No data found for {ticker}")
                return None
            
            df.reset_index(inplace=True)
            # Ensure 'Date' column is timezone-naive or normalized
            if 'Date' in df.columns and df['Date'].dt.tz is not None:
                 df['Date'] = df['Date'].dt.tz_convert(None)
                 
            # Store in cache
            market_data_cache[cache_key] = df.copy()

        if db:
            # Update database
            last_price = float(df.iloc[-1]["Close"])
            db_stock = db.query(Stock).filter(Stock.ticker == ticker).first()
            if not db_stock:
                try:
                    info = stock.info
                    company_name = info.get("shortName", ticker)
                except Exception:
                    company_name = ticker
                    
                db_stock = Stock(
                    ticker=ticker,
                    company_name=company_name,
                    last_price=last_price,
                    last_updated=datetime.utcnow()
                )
                db.add(db_stock)
            else:
                db_stock.last_price = last_price
                db_stock.last_updated = datetime.utcnow()
            
            db.commit()
            
        return df
    except Exception as e:
        logger.error(f"Error fetching data for {ticker}: {e}")
        return None
