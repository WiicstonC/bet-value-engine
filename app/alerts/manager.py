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
        (("england", "premier league", "epl", "soccer_epl"), "🇬🇧"),
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
    raw = event.competition.strip()
    key = raw.lower().replace("-", "_")
    labels = {
        "soccer_epl": "Premier League",
        "soccer_england_premier_league": "Premier League",
        "soccer_spain_la_liga": "La Liga",
        "soccer_germany_bundesliga": "Bundesliga",
        "soccer_italy_serie_a": "Serie A",
        "soccer_france_ligue_one": "Ligue 1",
        "soccer_colombia_primera_a": "Liga Colombiana",
        "soccer_colombia_primera_a_apertura": "Liga Colombiana",
        "basketball_nba": "NBA",
        "tennis_atp_cincinnati_open": "ATP Cincinnati",
        "tennis_wta_cincinnati_open": "WTA Cincinnati",
        "tennis_atp_us_open": "ATP US Open",
        "tennis_wta_us_open": "WTA US Open",
        "tennis_atp_canadian_open": "ATP Toronto",
        "tennis_wta_canadian_open": "WTA Toronto",
        "tennis_atp_madrid_open": "ATP Madrid",
        "tennis_wta_madrid_open": "WTA Madrid",
        "tennis_atp_rome": "ATP Roma",
        "tennis_wta_rome": "WTA Roma",
        "tennis_atp_monte_carlo": "ATP Monte Carlo",
        "tennis_atp_wimbledon": "ATP Wimbledon",
        "tennis_wta_wimbledon": "WTA Wimbledon",
        "tennis_atp_french_open": "ATP Roland Garros",
        "tennis_wta_french_open": "WTA Roland Garros",
    }
    if key in labels:
        return labels[key]
    # Fallback: never expose provider prefixes such as soccer_/basketball_.
    cleaned = raw.replace("soccer_", "").replace("basketball_", "").replace("tennis_", "")
    return cleaned.replace("_", " ").strip().title() or "Competición"


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
        f"{competition_flag(event)} {competition_label(event)}\n"
        f"{event.home} vs {event.away}\n"
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
        f"{competition_flag(event)} {competition_label(event)}\n"
        f"{event.home} vs {event.away}\n"
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


def _chunk_text(lines: list[str], limit: int = 3500) -> list[str]:
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


def _chunk_message_with_markup(message: str, markup: dict[str, Any] | None, limit: int = 3500) -> list[tuple[str, dict[str, Any] | None]]:
    """Telegram sendMessage has a 4096-char limit. Keep the action button on the final chunk."""
    if len(message) <= limit:
        return [(message, markup)]
    lines = message.splitlines()
    chunks = _chunk_text(lines, limit)
    return [(chunk, markup if index == len(chunks) - 1 else None) for index, chunk in enumerate(chunks)]


def format_daily_digest(events: list[Event], timezone_name: str, max_events: int = 45, preanalysis: dict[str, str] | None = None) -> tuple[list[str], list[dict[str, Any] | None]]:
    """Build compact Telegram cards. Selected events get their own deep-analysis button."""