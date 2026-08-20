from datetime import datetime
from pydantic import BaseModel, Field


class Event(BaseModel):
    event_id: str
    sport: str
    competition: str
    home: str
    away: str
    start_time: datetime
    status: str = "scheduled"


class Market(BaseModel):
    event_id: str
    market_id: str
    name: str
    selection: str
    odds: float = Field(gt=1.0)
    bookmaker: str
    updated_at: datetime


class Opportunity(BaseModel):
    event: Event
    market: Market
    model_probability: float
    implied_probability: float
    edge: float
    expected_value: float
    confidence: float
    decision: str
    risk_level: str
    alert_reasons: list[str] = Field(default_factory=list)
