from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.alerts.telegram import TelegramAlertSender
from app.config import AlertConfig, EngineConfig
from app.models import Candidate


def format_candidate(candidate: Candidate, timezone_name: str = "America/Bogota") -> str:
    event = candidate.event
    quote = candidate.quote
    line = f" {quote.line}" if quote.line is not None else ""
    local_start = event.start_time.astimezone(ZoneInfo(timezone_name)).strftime("%d/%m %H:%M")

    return (
        "🎯 BET VALUE ALERT\n\n"
        f"{event.sport.upper()} — {event.home} vs {event.away}\n"
        f"Inicio Colombia: {local_start}\n"
        f"Mercado: {quote.market}{line}\n"
        f"Selección: {quote.selection}\n"
        f"Casa objetivo: {quote.bookmaker}\n"
        f"Cuota: {quote.odds:.2f}\n\n"
        f"Consenso mercado: {candidate.model_probability:.2%}\n"
        f"Prob. implícita cuota: {candidate.implied_probability:.2%}\n"
        f"Edge: {candidate.edge:.2%}\n"
        f"EV estimado: {candidate.expected_value:.2%}\n"
        f"Confianza: {candidate.confidence:.1f}/100\n"
        f"Casas independientes: {candidate.consensus_bookmakers}\n"
        f"Dispersión consenso: {candidate.consensus_dispersion:.3%}\n"
        f"Decisión: {candidate.decision}\n\n"
        "⚠️ Señal estadística basada en consenso de cuotas; no garantiza resultado."
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
            if sent >= self.config.alerts.max_alerts_per_scan:
                break
            if not alert_due(candidate, self.config.alerts, self.config.scan_interval_minutes):
                continue
            if self.sender.send(format_candidate(candidate, self.config.timezone)):
                sent += 1
        return sent
