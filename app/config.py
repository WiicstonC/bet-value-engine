import json
from pathlib import Path

from pydantic import BaseModel, Field


class AlertConfig(BaseModel):
    enabled: bool = True
    minutes_before_start: list[int] = Field(default_factory=lambda: [360, 60, 10])
    minimum_confidence: float = 75.0
    minimum_edge: float = 0.05
    minimum_expected_value: float = 0.05
    minimum_consensus_bookmakers: int = Field(default=3, ge=1, le=10)
    max_alerts_per_scan: int = Field(default=5, ge=1, le=20)


class WatchlistConfig(BaseModel):
    sports: list[str] = Field(default_factory=lambda: ["tennis", "football", "nba"])
    competitions: list[str] = Field(default_factory=list)
    teams: list[str] = Field(default_factory=list)
    players: list[str] = Field(default_factory=list)
    markets: list[str] = Field(default_factory=lambda: ["h2h", "spreads", "totals"])
    bookmakers: list[str] = Field(default_factory=lambda: ["Betano"])


class EngineConfig(BaseModel):
    timezone: str = "America/Bogota"
    scan_interval_minutes: int = Field(default=10, ge=1, le=60)
    watch_hours: int = Field(default=48, ge=1, le=168)
    watchlist: WatchlistConfig = Field(default_factory=WatchlistConfig)
    alerts: AlertConfig = Field(default_factory=AlertConfig)


def load_config() -> EngineConfig:
    path = Path(__file__).resolve().parent.parent / "config" / "watchlist.json"
    if not path.exists():
        return EngineConfig()

    with path.open("r", encoding="utf-8") as file:
        return EngineConfig.model_validate(json.load(file))


DEFAULT_CONFIG = load_config()
