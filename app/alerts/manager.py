from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from app.alerts.telegram import TelegramAlertSender
from app.config import AlertConfig, EngineConfig
from app.models import Candidate, Event


def _local_start(event: Event, timezone_name: str) -> str:
    return event.start_time.astimezone(ZoneInfo(timezone_name)).strftime("%d/%m %H:%M")


def competition_flag(event: Event) -> str:
    text = f"{event.competition} {event.home} {event.away}".lower()
    mappings = [
        (("england", "premier league", "epl", "soccer_epl"), "🏴"),
        (("spain", "la liga", "laliga", "soccer_spain"), "🇪🇸"),
        (("germany", "bundesliga", "soccer_germany"), "🇩🇪"),
        (("italy", "serie a", "soccer_italy"), "🇮🇹"),
        (("france", "ligue 1", "ligue one", "soccer_france"), "🇫🇷"),
        (("colombia", "primera a", "liga betplay", "dimayor", "soccer_colombia"), "🇨🇴"),
        (("nba", "basketball_nba"), "🇺🇸"),
        (("cincinnati", "indian wells", "miami open", "us open", "washington open"), "🇺🇸"),
        (("wimbledon", "queens", "queen's", "halle", "bad homburg", "stuttgart", "german open"), "🇬🇧"),
        (("french open", "roland garros"), "🇫🇷"),
        (("madrid", "barcelona", "mutua"), "🇪🇸"),
        (("rome", "italian open", "rome masters"), "🇮🇹"),
        (("monte carlo", "monaco"), "🇲🇨"),
        (("shanghai", "china open", "beijing"), "🇨🇳"),
        (("tokyo", "japan open"), "🇯🇵"),
        (("dubai", "qatar"), "🇦🇪"),
    ]
    for keywords, flag in mappings:
        if any(keyword in text for keyword in keywords):
            return flag
    return "🌐"


def competition_label(event: Event) -> str:
    return event.competition.strip() or event.sport.upper()


def deep_button(event: Event) -> dict[str, Any]:
    callback_data = f"deep|{event.sport}|{event.id}"
    if len(callback_data.encode("utf-8")) > 64:
        raise ValueError(f"Event ID demasiado largo para callback_data: {event.id}")
    return {"inline_keyboard": [[{"text": "🔬 Analizar a fondo", "callback_data": callback_data}]]}


def format_candidate(candidate: Candidate, timezone_name: str = "America/Bogota") -> str:
    event, quote = candidate.event, candidate.quote
    line = f" {quote.line}" if quote.line is not None else ""
    return (
        "🎯 BET VALUE ALERT\n\n"
        f"{event.sport.upper()} — {event.home} vs {event.away}\n"
        f"Inicio Colombia: {_local_start(event, timezone_name)}\n"
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


def format_live_candidate(candidate: Candidate, timezone_name: str = "America/Bogota", incident_text: str | None = None) -> str:
    event, quote = candidate.event, candidate.quote
    line = f" {quote.line}" if quote.line is not None else ""
    incident = f"\n⚡ Evento detectado: {incident_text}\n" if incident_text else ""
    return (
        "🚨 OPORTUNIDAD EN VIVO\n\n"
        f"{event.sport.upper()} — {event.home} vs {event.away}\n"
        f"Comenzó: {_local_start(event, timezone_name)}\n"
        f"Mercado: {quote.market}{line}\n"
        f"Selección: {quote.selection}\n"
        f"Cuota Betano: {quote.odds:.2f}\n"
        f"{incident}\n"
        f"Probabilidad consenso: {candidate.model_probability:.2%}\n"
        f"Edge: {candidate.edge:.2%}\n"
        f"EV: {candidate.expected_value:.2%}\n"
        f"Confianza: {candidate.confidence:.1f}/100\n"
        f"Casas independientes: {candidate.consensus_bookmakers}\n\n"
        "⚠️ Confirma marcador, tiempo y novedades antes de apostar."
    )


def _chunk_text(lines: list[str], limit: int = 3900) -> list[str]:
    chunks, current = [], ""
    for line in lines:
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            if current:
                chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def format_daily_digest(events: list[Event], timezone_name: str, max_events: int = 45, preanalysis: dict[str, str] | None = None) -> tuple[list[str], list[dict[str, Any] | None]]:
    """Build compact Telegram cards. Selected events get their own deep-analysis button."""
    local_tz = ZoneInfo(timezone_name)
    ordered = sorted(events, key=lambda event: event.start_time)[:max_events]
    total = len(events)
    messages = [
        "📅 AGENDA DEPORTIVA",
        "",
        f"Eventos encontrados: {total}",
        "🧠 Preanálisis cualitativo: activo",
        "💳 Cuotas todavía NO consultadas para estos eventos.",
    ]
    markups: list[dict[str, Any] | None] = [None]
    selected_ids: set[str] = set()

    if preanalysis:
        selected = sorted(((event, preanalysis[event.id]) for event in ordered if event.id in preanalysis), key=lambda pair: pair[0].start_time)
        selected_ids = {event.id for event, _ in selected}
        for event, analysis in selected:
            local = event.start_time.astimezone(local_tz)
            messages.append(
                f"{competition_flag(event)} {competition_label(event)}\n"
                f"{event.sport.upper()} | {event.home} vs {event.away}\n"
                f"🕒 {local.strftime('%d/%m %H:%M')} Colombia\n\n"
                f"{analysis}\n\n"
                "💡 El preanálisis decide si vale la pena gastar un crédito en mercados/cuotas."
            )
            markups.append(deep_button(event))

    remainder_lines = ["📋 RESTO DE LA AGENDA", ""]
    remainder_events = [event for event in ordered if event.id not in selected_ids]
    for event in remainder_events:
        local = event.start_time.astimezone(local_tz)
        remainder_lines.append(
            f"{competition_flag(event)} {local.strftime('%d/%m %H:%M')} | "
            f"{event.sport.upper()} | {event.home} vs {event.away} | {competition_label(event)}"
        )
    if not remainder_events:
        remainder_lines.append("Todos los eventos seleccionados aparecen arriba para revisión.")
    if total > max_events:
        remainder_lines += ["", f"…y {total - max_events} eventos más."]
    remainder = _chunk_text(remainder_lines)
    messages.extend(remainder)
    markups.extend([None] * len(remainder))
    return messages, markups


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

    def notify_live(self, candidates: list[Candidate], incident_text: str | None = None) -> int:
        sent = 0
        for candidate in candidates[: self.config.live.max_alerts_per_run]:
            if self.sender.send(format_live_candidate(candidate, self.config.timezone, incident_text)):
                sent += 1
        return sent

    def send_daily_digest(self, events: list[Event], preanalysis: dict[str, str] | None = None) -> int:
        messages, markups = format_daily_digest(events, self.config.timezone, self.config.daily_digest.max_events_per_message, preanalysis)
        return self.sender.send_many(messages, markups)
