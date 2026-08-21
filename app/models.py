from datetime import datetime

from pydantic import BaseModel, Field


class Event(BaseModel):
    id: str
    sport: str
    competition: str
    home: str
    away: str
    start_time: datetime


class MarketQuote(BaseModel):
    event_id: str
    market: str
    selection: str
    line: float | None = None
    odds: float = Field(gt=1.0)
    bookmaker: str
    updated_at: datetime


class Candidate(BaseModel):
    event: Event
    quote: MarketQuote
    model_probability: float
    implied_probability: float
    edge: float
    expected_value: float
    confidence: float
    decision: str
    consensus_bookmakers: int = 0
    consensus_dispersion: float = 0.0
