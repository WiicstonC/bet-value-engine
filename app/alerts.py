from datetime import datetime, timedelta

from app.config import AlertConfig
from app.data_models import Opportunity


def should_alert(opportunity: Opportunity, config: AlertConfig, now: datetime) -> bool:
    if not config.enabled:
        return False

    if opportunity.confidence < config.minimum_confidence:
        return False

    if opportunity.edge < config.minimum_edge:
        return False

    if opportunity.expected_value < config.minimum_expected_value:
        return False

    if opportunity.decision == "NO_VALUE":
        return False

    minutes_to_start = (
        opportunity.event.start_time - now
    ).total_seconds() / 60

    windows = config.minutes_before_start

    return any(
        0 <= minutes_to_start <= window
        for window in windows
    )


def alert_message(opportunity: Opportunity, minutes_to_start: float) -> str:
    return (
        f"BET VALUE ALERT | {opportunity.event.sport.upper()} | "
        f"{opportunity.event.home} vs {opportunity.event.away} | "
        f"{opportunity.market.name}: {opportunity.market.selection} | "
        f"Cuota {opportunity.market.odds:.2f} | "
        f"Prob. modelo {opportunity.model_probability:.1%} | "
        f"Edge {opportunity.edge:.1%} | "
        f"EV {opportunity.expected_value:.1%} | "
        f"Confidence {opportunity.confidence:.0f} | "
        f"Inicio en {max(0, minutes_to_start):.0f} min"
    )
