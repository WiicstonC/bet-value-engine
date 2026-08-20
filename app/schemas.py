from typing import Literal

from pydantic import BaseModel, Field, field_validator


Sport = Literal["tennis", "football", "nba"]


class BetAnalysisRequest(BaseModel):
    sport: Sport
    market: str = Field(min_length=2, max_length=100)
    selection: str = Field(min_length=1, max_length=100)

    odds: float = Field(gt=1.0, le=1000.0)

    model_probability: float = Field(
        gt=0.0,
        lt=1.0,
        description="Probabilidad estimada por nuestro modelo, entre 0 y 1.",
    )

    confidence_inputs: dict[str, float] | None = None

    @field_validator("model_probability")
    @classmethod
    def validate_probability(cls, value: float) -> float:
        if not 0 < value < 1:
            raise ValueError("model_probability debe estar entre 0 y 1")
        return value


class BetAnalysisResponse(BaseModel):
    sport: str
    market: str
    selection: str

    odds: float

    implied_probability: float
    model_probability: float

    edge: float
    expected_value: float

    confidence: float
    decision: str

    risk_level: str
    reasons: list[str]
