from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from database import Base
import datetime

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)

    preferences = relationship("UserPreference", back_populates="user", uselist=False)
    watchlist = relationship("Watchlist", back_populates="user")

class UserPreference(Base):
    __tablename__ = "user_preferences"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    risk_level = Column(String, default="Medium")
    investment_type = Column(String, default="Long-term")
    focus_type = Column(String, default="Technical")
    budget_range = Column(String, nullable=True)
    expected_return = Column(String, nullable=True)

    user = relationship("User", back_populates="preferences")

class Stock(Base):
    __tablename__ = "stocks"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String, unique=True, index=True)
    company_name = Column(String)
    last_price = Column(Float, nullable=True)
    last_updated = Column(DateTime, default=datetime.datetime.utcnow)

class TechnicalSignal(Base):
    __tablename__ = "technical_signals"

    id = Column(Integer, primary_key=True, index=True)
    stock_id = Column(Integer, ForeignKey("stocks.id"), unique=True)
    rsi = Column(Float, nullable=True)
    macd = Column(Float, nullable=True)
    sma20 = Column(Float, nullable=True)
    sma50 = Column(Float, nullable=True)
    sma200 = Column(Float, nullable=True)
    volatility = Column(Float, nullable=True)

class SentimentData(Base):
    __tablename__ = "sentiment_data"

    id = Column(Integer, primary_key=True, index=True)
    stock_id = Column(Integer, ForeignKey("stocks.id"))
    sentiment_score = Column(Float, nullable=True)
    sentiment_label = Column(String, nullable=True)
    headline = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

class Watchlist(Base):
    __tablename__ = "watchlist"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    ticker = Column(String, index=True)

    user = relationship("User", back_populates="watchlist")

class Recommendation(Base):
    __tablename__ = "recommendations"
    
    id = Column(Integer, primary_key=True, index=True)
    stock_id = Column(Integer, ForeignKey("stocks.id"), unique=True)
    recommendation = Column(String) # BUY / HOLD / SELL
    confidence_score = Column(Float) # 0-100
    trend_direction = Column(String)
    risk_level = Column(String)
    explanation_text = Column(Text)
