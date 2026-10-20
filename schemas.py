import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=30, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(..., min_length=8, max_length=128)


class UserLogin(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=128)


class Token(BaseModel):
    access_token: str
    token_type: str
    username: str | None = None


class TokenData(BaseModel):
    username: str | None = None


class PreferenceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    risk_level: Literal["Low", "Medium", "High"] | None = None
    investment_type: Literal["Short-term", "Long-term"] | None = None
    focus_type: Literal["Technical", "Fundamental", "Sentiment"] | None = None
    budget_range: str | None = None
    expected_return: str | None = None


class PreferenceOut(BaseModel):
    user_id: int
    risk_level: str | None = None
    investment_type: str | None = None
    focus_type: str | None = None
    budget_range: str | None = None
    expected_return: str | None = None

    model_config = ConfigDict(from_attributes=True)


class UserProfileOut(BaseModel):
    id: int
    username: str
    watchlist_count: int
    preferences: PreferenceOut | None = None


class ChangePasswordIn(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)


class TechSummary(BaseModel):
    tech_score: float | None = None
    numerical_evidence: list[str] = []
    rsi: float | None = None
    macd: float | None = None
    sma20: float | None = None
    sma50: float | None = None
    sma200: float | None = None
    volatility: float | None = None
    interpretations: dict | None = None
    available: bool | None = True


class SentimentSummary(BaseModel):
    sentiment_score: float
    sentiment_label: str
    summary_text: str


class FunMetricSummary(BaseModel):
    pe_ratio: float | None
    eps: float | None
    revenue_growth: float | None
    profit_margins: float | None
    debt_to_equity: float | None


class FundSummary(BaseModel):
    fundamental_score: float | None = None
    numerical_evidence: list[str] = []
    metrics: FunMetricSummary | None = None
    available: bool | None = True


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

    @field_validator("ticker")
    @classmethod
    def validate_ticker(cls, v: str) -> str:
        cleaned = v.strip().upper()
        if not re.match(r"^[A-Z.\-]{1,10}$", cleaned):
            raise ValueError(f"Invalid ticker '{v}'. Must match regex ^[A-Z.\\-]{{1,10}}$")
        return cleaned


class WatchlistOut(WatchlistAdd):
    id: int
    user_id: int

    model_config = ConfigDict(from_attributes=True)


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
