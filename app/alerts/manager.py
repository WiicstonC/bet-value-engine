from datetime import datetime, timezone

from app.alerts.telegram import TelegramAlertSender
from app.config import AlertConfig, EngineConfig
from app.models import Candidate


def format_candidate(candidate: Candidate) -> str:
    event = candidate.event
    quote = candidate.quote
    line = f" {quote.line}" if quote.line is not None else ""
    start = event.start_time.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return (
        "🎯 BET VALUE ALERT\n\n"
        f"{event.sport.upper()} — {event.home} vs {event.away}\n"
        f"Start: {start}\n"
        f"Market: {quote.market}{line}\n"
        f"Selection: {quote.selection}\n"
        f"Bookmaker: {quote.bookmaker}\n"
        f"Odds: {quote.odds:.2f}\n"
        f"Model probability: {candidate.model_probability:.2%}\n"
        f"Betano probability: {candidate.implied_probability:.2%}\n"
        f"Edge: {candidate.edge:.2%}\n"
        f"EV: {candidate.expected_value:.2%}\n"
        f"Confidence: {candidate.confidence:.1f}/100\n"
        f"Decision: {candidate.decision}\n\n"
        "⚠️ Señal estadística; no garantiza resultado."
    )


def alert_due(candidate: Candidate, alert_config: AlertConfig, scan_interval_minutes: int) -> bool:
    now = datetime.now(timezone.utc)
    minutes_to_start = (candidate.event.start_time - now).total_seconds() / 60
    half_window = max(scan_interval_minutes / 2, 2)
    return any(
        target - half_window <= minutes_to_start <= target + half_window
        for target in alert_config.minutes_before_start
    )


class AlertManager:
    def __init__(self, sender: TelegramAlertSender, config: EngineConfig):
        self.sender = sender
        self.config = config

    def notify(self, candidates: list[Candidate]) -> int:
        sent = 0
        for candidate in candidates:
            if not alert_due(candidate, self.config.alerts, self.config.scan_interval_minutes):
                continue
            if self.sender.send(format_candidate(candidate)):
                sent += 1
        return sent
