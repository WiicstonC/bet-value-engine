from math import exp
from pydantic import BaseModel, Field


class TennisPlayerStats(BaseModel):
    elo: float = 1500.0
    surface_elo: float = 1500.0
    hold_rate: float = Field(0.80, ge=0.0, le=1.0)
    break_rate: float = Field(0.20, ge=0.0, le=1.0)
    first_serve_points_won: float = Field(0.70, ge=0.0, le=1.0)
    second_serve_points_won: float = Field(0.50, ge=0.0, le=1.0)
    return_points_won: float = Field(0.35, ge=0.0, le=1.0)
    aces_per_match: float = Field(5.0, ge=0.0)
    double_faults_per_match: float = Field(2.0, ge=0.0)
    recent_form: float = Field(0.50, ge=0.0, le=1.0)
    fatigue: float = Field(0.0, ge=0.0, le=1.0)
    injury_risk: float = Field(0.0, ge=0.0, le=1.0)
    weather_impact: float = Field(0.0, ge=0.0, le=1.0)


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + exp(-x))


def win_probability(player_a: TennisPlayerStats, player_b: TennisPlayerStats) -> float:
    elo_delta = (player_a.elo - player_b.elo) / 400.0
    surface_delta = (player_a.surface_elo - player_b.surface_elo) / 400.0
    hold_delta = (player_a.hold_rate - player_b.hold_rate) * 3.0
    break_delta = (player_a.break_rate - player_b.break_rate) * 3.0
    serve_delta = (
        (player_a.first_serve_points_won - player_b.first_serve_points_won) * 2.0
        + (player_a.second_serve_points_won - player_b.second_serve_points_won) * 2.0
    )
    return_delta = (player_a.return_points_won - player_b.return_points_won) * 2.0
    form_delta = (player_a.recent_form - player_b.recent_form) * 1.5
    ace_delta = (player_a.aces_per_match - player_b.aces_per_match) * 0.03
    df_delta = (player_b.double_faults_per_match - player_a.double_faults_per_match) * 0.04

    fatigue_delta = (player_b.fatigue - player_a.fatigue) * 1.5
    injury_delta = (player_b.injury_risk - player_a.injury_risk) * 2.5
    weather_delta = (player_b.weather_impact - player_a.weather_impact) * 0.8

    score = (
        elo_delta
        + surface_delta
        + hold_delta
        + break_delta
        + serve_delta
        + return_delta
        + form_delta
        + ace_delta
        + df_delta
        + fatigue_delta
        + injury_delta
        + weather_delta
    )

    return round(_sigmoid(score), 6)
