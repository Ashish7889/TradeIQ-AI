from pydantic import BaseModel
from typing import Optional, List, Any

class UserCreate(BaseModel):
    username: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

class PreferenceUpdate(BaseModel):
    risk_level: Optional[str] = "Medium"
    investment_type: Optional[str] = "Long-term"
    focus_type: Optional[str] = "Technical"
    budget_range: Optional[str] = None
    expected_return: Optional[str] = None

class PreferenceOut(PreferenceUpdate):
    user_id: int

    class Config:
        from_attributes = True

class TechSummary(BaseModel):
    tech_score: float
    numerical_evidence: List[str]
    rsi: Optional[float]
    macd: Optional[float]
    sma20: Optional[float]
    sma50: Optional[float]
    sma200: Optional[float]
    volatility: Optional[float]
    interpretations: dict

class SentimentSummary(BaseModel):
    sentiment_score: float
    sentiment_label: str
    summary_text: str
    
class FunMetricSummary(BaseModel):
    pe_ratio: Optional[float]
    eps: Optional[float]
    revenue_growth: Optional[float]
    profit_margins: Optional[float]
    debt_to_equity: Optional[float]

class FundSummary(BaseModel):
    fundamental_score: float
    numerical_evidence: List[str]
    metrics: FunMetricSummary

class ScoreBreakdown(BaseModel):
    technical: float
    fundamental: float
    sentiment: float
    risk: float

class AnalysisReportOut(BaseModel):
    ticker: str
    final_score: float
    recommendation: str
    confidence_score: float
    score_breakdown: ScoreBreakdown
    report: str
    full_data: Any

class WatchlistAdd(BaseModel):
    ticker: str

class WatchlistOut(WatchlistAdd):
    id: int
    user_id: int
    
    class Config:
        from_attributes = True

class RecommendationScoreBreakdown(BaseModel):
    technical: float
    fundamental: float
    sentiment: float

class RecommendationOut(BaseModel):
    recommendation: str
    confidence_score: float
    trend_direction: str
    risk_level: str
    explanation_text: str
    portfolio_allocation: str
    price_prediction: str
    score_breakdown: RecommendationScoreBreakdown
