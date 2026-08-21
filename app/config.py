import json
from pathlib import Path

from pydantic import BaseModel, Field


class AlertConfig(BaseModel):
    enabled: bool = True
    minutes_before_start: list[int] = Field(default_factory=lambda: [10])
    minimum_confidence: float = 75.0
    minimum_edge: float = 0.05
    minimum_expected_value: float = 0.05
    minimum_consensus_bookmakers: int = Field(default=3, ge=1, le=10)
    max_alerts_per_scan: int = Field(default=5, ge=1, le=20)


class DeepScanConfig(BaseModel):
    enabled: bool = True
    minutes_before_start: int = 60
    max_events_per_run: int = Field(default=8, ge=1, le=30)
    max_markets_per_event: int = Field(default=6, ge=1, le=20)
    only_if_target_bookmaker_has_market: bool = True
    manual_only: bool = True


class DailyDigestConfig(BaseModel):
    enabled: bool = True
    hour_local: int = Field(default=6, ge=0, le=23)
    days_ahead: int = Field(default=1, ge=1, le=3)
    max_events_per_message: int = Field(default=45, ge=5, le=100)


class LiveConfig(BaseModel):
    enabled: bool = True
    interval_minutes: int = Field(default=10, ge=5, le=60)
    lookback_minutes: int = Field(default=240, ge=30, le=720)
    markets: list[str] = Field(default_factory=lambda: ["h2h"])
    minimum_confidence: float = 78.0
    minimum_edge: float = 0.07
    minimum_expected_value: float = 0.07
    max_alerts_per_run: int = Field(default=3, ge=1, le=10)
    price_shock_percent: float = Field(default=12.0, ge=1.0, le=90.0)
    persist_state: bool = True


class ApiPoolConfig(BaseModel):
    enabled: bool = True
    key_env_names: list[str] = Field(default_factory=lambda: [
        "ODDS_API_KEY",
        "ODDS_API_KEY_2",
        "ODDS_API_KEY_3",
    ])


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
    watch_hours: int = Field(default=24, ge=1, le=168)
    watchlist: WatchlistConfig = Field(default_factory=WatchlistConfig)
    alerts: AlertConfig = Field(default_factory=AlertConfig)
    deep_scan: DeepScanConfig = Field(default_factory=DeepScanConfig)
    daily_digest: DailyDigestConfig = Field(default_factory=DailyDigestConfig)
    live: LiveConfig = Field(default_factory=LiveConfig)
    api_pool: ApiPoolConfig = Field(default_factory=ApiPoolConfig)


def load_config() -> EngineConfig:
    path = Path(__file__).resolve().parent.parent / "config" / "watchlist.json"
    if not path.exists():
        return EngineConfig()

    with path.open("r", encoding="utf-8") as file:
        return EngineConfig.model_validate(json.load(file))


DEFAULT_CONFIG = load_config()
