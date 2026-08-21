from collections import defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.alerts.telegram import TelegramAlertSender
from app.config import AlertConfig, EngineConfig
from app.models import Candidate, Event


def _local_start(event: Event, timezone_name: str) -> str:
    return event.start_time.astimezone(ZoneInfo(timezone_name)).strftime("%d/%m %H:%M")


def format_candidate(candidate: Candidate, timezone_name: str = "America/Bogota") -> str:
    event = candidate.event
    quote = candidate.quote
    line = f" {quote.line}" if quote.line is not None else ""
    local_start = _local_start(event, timezone_name)

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


def format_live_candidate(candidate: Candidate, timezone_name: str = "America/Bogota") -> str:
    event = candidate.event
    quote = candidate.quote
    line = f" {quote.line}" if quote.line is not None else ""
    return (
        "🚨 OPORTUNIDAD EN VIVO\n\n"
        f"{event.sport.upper()} — {event.home} vs {event.away}\n"
        f"Comenzó: {_local_start(event, timezone_name)}\n"
        f"Mercado: {quote.market}{line}\n"
        f"Selección: {quote.selection}\n"
        f"Cuota Betano: {quote.odds:.2f}\n\n"
        f"Probabilidad consenso: {candidate.model_probability:.2%}\n"
        f"Edge: {candidate.edge:.2%}\n"
        f"EV: {candidate.expected_value:.2%}\n"
        f"Confianza: {candidate.confidence:.1f}/100\n"
        f"Casas independientes: {candidate.consensus_bookmakers}\n\n"
        "⚠️ El motor detectó valor con el mercado actual. Confirma el marcador, tiempo de juego y novedades del partido antes de apostar."
    )


def format_daily_digest(events: list[Event], timezone_name: str, max_events: int = 45) -> list[str]:
    """Build Telegram messages containing events only; no odds requests are made here."""
    local_tz = ZoneInfo(timezone_name)
    grouped: dict[tuple[str, str], list[Event]] = defaultdict(list)
    for event in events:
        local = event.start_time.astimezone(local_tz)
        grouped[(local.strftime("%d/%m"), event.competition)].append(event)

    ordered = sorted(
        events,
        key=lambda event: event.start_time,
    )[:max_events]
    total = len(events)
    lines = [
        "📅 AGENDA DEPORTIVA DEL DÍA",
        "",
        f"Eventos encontrados: {total}",
        "Sin análisis de cuotas todavía: 0 créditos de odds gastados por este mensaje.",
        "",
    ]

    for event in ordered:
        local = event.start_time.astimezone(local_tz)
        lines.append(
            f"• {local.strftime('%d/%m %H:%M')} | {event.sport.upper()} | "
            f"{event.home} vs {event.away} | {event.competition} | ID {event.id}"
        )

    if total > max_events:
        lines.append("")
        lines.append(f"…y {total - max_events} eventos más. Usa el ID de un evento para solicitar análisis profundo.")

    header = "\n".join(lines)
    if len(header) <= 3900:
        return [header]

    chunks: list[str] = []
    current = ""
    for line in lines:
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > 3900:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def alert_due(candidate: Candidate, alert_config: AlertConfig, scan_interval_minutes: int) -> bool:
    now = datetime.now(timezone.utc)
    minutes_to_start = (candidate.event.start_time - now).total_seconds() / 60
    half_window = max(scan_interval_minutes / 2, 2)
    return any(target - half_window <= minutes_to_start <= target + half_window for target in alert_config.minutes_before_start)


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

    def notify_live(self, candidates: list[Candidate]) -> int:
        sent = 0
        for candidate in candidates[: self.config.live.max_alerts_per_run]:
            if self.sender.send(format_live_candidate(candidate, self.config.timezone)):
                sent += 1
        return sent

    def send_daily_digest(self, events: list[Event]) -> int:
        messages = format_daily_digest(
            events,
            self.config.timezone,
            self.config.daily_digest.max_events_per_message,
        )
        return self.sender.send_many(messages)
