import logging
import threading
from datetime import datetime

import yfinance as yf
from cachetools import TTLCache
from sqlalchemy.orm import Session

from models import Stock

logger = logging.getLogger(__name__)

# Institutional-grade caching: 15 min TTL, max 200 items to prevent memory bloat
market_data_cache = TTLCache(maxsize=200, ttl=900)
_cache_lock = threading.Lock()


def fetch_stock_data(ticker: str, period: str = "1y", db: Session = None):
    """
    Fetches historical OHLCV data for a ticker using yfinance.
    Saves/updates the stock in the database if db is provided.
    Returns the pandas DataFrame.
    """
    ticker = ticker.upper()
    cache_key = f"{ticker}_{period}"

    try:
        # Check cache first with lock
        with _cache_lock:
            cached_df = market_data_cache.get(cache_key)
            if cached_df is not None:
                df = cached_df.copy()
            else:
                df = None

        if df is not None:
            logger.info(f"[Cache Hit] Market data for {cache_key}")
        else:
            logger.info(f"[Cache Miss] Fetching data for {cache_key} from Yahoo Finance")
            stock = yf.Ticker(ticker)
            df = stock.history(period=period)

            if (df is None or df.empty) and period == "1d":
                logger.info(f"period=1d returned empty for {ticker}, falling back to 5d")
                df = stock.history(period="5d")

            if df is None or df.empty:
                logger.warning(f"No data found for {ticker}")
                return None

            df.reset_index(inplace=True)
            # Ensure 'Date' column is timezone-naive or normalized
            if "Date" in df.columns and df["Date"].dt.tz is not None:
                df["Date"] = df["Date"].dt.tz_convert(None)

            # Store in cache with lock
            with _cache_lock:
                market_data_cache[cache_key] = df.copy()

        if db:
            try:
                # Update database
                last_price = float(df.iloc[-1]["Close"])
                db_stock = db.query(Stock).filter(Stock.ticker == ticker).first()
                if not db_stock:
                    company_name = ticker
                    try:
                        if "stock" in locals() and stock is not None:
                            info = stock.info
                            if isinstance(info, dict):
                                company_name = info.get("shortName") or info.get("longName") or ticker
                    except Exception as info_err:
                        logger.warning(f"Could not fetch company name for {ticker}: {info_err}")
                        company_name = ticker

                    db_stock = Stock(
                        ticker=ticker, company_name=company_name, last_price=last_price, last_updated=datetime.utcnow()
                    )
                    db.add(db_stock)
                else:
                    db_stock.last_price = last_price
                    db_stock.last_updated = datetime.utcnow()

                db.commit()
            except Exception as db_err:
                logger.warning(f"Database sync failed for {ticker}: {db_err}")
                try:
                    db.rollback()
                except Exception as rollback_err:
                    logger.debug(f"Rollback failed: {rollback_err}")

        return df
    except Exception as e:
        logger.exception(f"Error fetching data for {ticker}: {e}")
        return None
