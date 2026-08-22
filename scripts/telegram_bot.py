import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from app.alerts.manager import competition_flag, competition_label
from app.alerts.telegram import TelegramAlertSender
from app.analysis.preanalysis import generate_preanalysis
from app.config import DEFAULT_CONFIG
from app.engine.scanner import Scanner
from app.learning.ledger import offer_candidate, register_offer
from app.providers.odds_api import TheOddsAPIProvider
from app.providers.selected_events import events_for_keys

STATE_PATH = Path(__file__).resolve().parent.parent / "data" / "telegram_offset_v2.json"

COUNTRIES = {
    "🇨🇴 Colombia": [("Liga Colombiana", "soccer_colombia_primera_a"), ("Copa Colombia", "soccer_colombia_cup")],
    "🇪🇸 España": [("La Liga", "soccer_spain_la_liga"), ("Copa del Rey", "soccer_spain_copa_del_rey"), ("LaLiga 2", "soccer_spain_segunda_division")],
    "🇬🇧 Inglaterra": [("Premier League", "soccer_epl"), ("FA Cup", "soccer_fa_cup"), ("Championship", "soccer_efl_champ"), ("EFL Cup", "soccer_england_efl_cup")],
    "🇩🇪 Alemania": [("Bundesliga", "soccer_germany_bundesliga"), ("DFB-Pokal", "soccer_germany_dfb_pokal"), ("Bundesliga 2", "soccer_germany_bundesliga2")],
    "🇮🇹 Italia": [("Serie A", "soccer_italy_serie_a"), ("Coppa Italia", "soccer_italy_coppa_italia"), ("Serie B", "soccer_italy_serie_b")],
    "🇫🇷 Francia": [("Ligue 1", "soccer_france_ligue_one"), ("Coupe de France", "soccer_france_coupe_de_france"), ("Ligue 2", "soccer_france_ligue_two")],
}

COUNTRY_CODES = {
    "co": "🇨🇴 Colombia", "es": "🇪🇸 España", "gb": "🇬🇧 Inglaterra",
    "de": "🇩🇪 Alemania", "it": "🇮🇹 Italia", "fr": "🇫🇷 Francia",
}

TENNIS = [
    ("🎾 ATP — torneo actual", "tennis_atp_active"),
    ("🎾 WTA — torneo actual", "tennis_wta_active"),
]


def load_offset():
    if not STATE_PATH.exists():
        return None
    try:
        return int(json.loads(STATE_PATH.read_text(encoding="utf-8")).get("offset"))
    except Exception:
        return None


def save_offset(offset):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps({"offset": offset}), encoding="utf-8")


def menu_keyboard():
    return {"inline_keyboard": [
        [{"text": "🇨🇴 Colombia", "callback_data": "country|co"}, {"text": "🇪🇸 España", "callback_data": "country|es"}],
        [{"text": "🇬🇧 Inglaterra", "callback_data": "country|gb"}, {"text": "🇩🇪 Alemania", "callback_data": "country|de"}],
        [{"text": "🇮🇹 Italia", "callback_data": "country|it"}, {"text": "🇫🇷 Francia", "callback_data": "country|fr"}],
        [{"text": "🏀 NBA", "callback_data": "competition|basketball_nba"}, {"text": "🎾 Tenis", "callback_data": "tennis|root"}],
        [{"text": "🌅 Mañana completa", "callback_data": "day|tomorrow"}, {"text": "📅 Hoy completo", "callback_data": "day|today"}],
        [{"text": "🔴 En vivo", "callback_data": "live|root"}],
    ]}


def quick_keyboard():
    return {"keyboard": [[{"text": "📋 Menú"}, {"text": "🌅 Mañana"}], [{"text": "📅 Hoy"}, {"text": "🔴 En vivo"}]], "resize_keyboard": True, "is_persistent": True}


def country_keyboard(code):
    rows = [[{"text": f"⚽ {label}", "callback_data": f"competition|{key}"}] for label, key in COUNTRIES[COUNTRY_CODES[code]]]
    rows.append([{"text": "⬅️ Volver", "callback_data": "menu|root"}])
    return {"inline_keyboard": rows}


def tennis_keyboard():
    rows = [[{"text": label, "callback_data": f"competition|{key}"}] for label, key in TENNIS]
    rows.append([{"text": "⬅️ Volver", "callback_data": "menu|root"}])
    return {"inline_keyboard": rows}


def period_keyboard(competition):
    return {"inline_keyboard": [
        [{"text": "📅 Hoy", "callback_data": f"league|{competition}|today"}, {"text": "🌅 Mañana", "callback_data": f"league|{competition}|tomorrow"}],
        [{"text": "⬅️ Volver", "callback_data": "menu|root"}],
    ]}


def deep_button(event):
    return {"inline_keyboard": [[{"text": "🔬 Analizar a fondo", "callback_data": f"deep|{event.sport}|{event.id}"}]]}


def track_button(prediction_id):
    return {"inline_keyboard": [[{"text": "🎯 Seguir pronóstico", "callback_data": f"track|{prediction_id}"}]]}


def send_menu(sender, intro=False):
    sender.send(
        "🤖 BET VALUE ENGINE\n\n"
        "Tú decides qué consultar. Selecciona una bandera, NBA, Tenis o la agenda.\n\n"
        "💳 Las cuotas y mercados especializados NO se consultan hasta que pulses 🔬 Analizar a fondo.\n"
        "🧠 El preanálisis es la primera capa del motor: contexto, forma, bajas, calendario y mercados que merece la pena investigar.",
        menu_keyboard(),
    )
    if intro:
        sender.send("📌 Control rápido disponible abajo.", quick_keyboard())


def event_window(day):
    tz = ZoneInfo(DEFAULT_CONFIG.timezone)
    now = datetime.now(tz)
    target = now.date() if day == "today" else (now + timedelta(days=1)).date()
    start_local = datetime.combine(target, datetime.min.time(), tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def fetch_competition_events(provider, competition, day):
    start, end = event_window(day)
    if competition == "tennis_atp_active":
        keys = [k for k in provider.active_sport_keys("tennis") if k.startswith("tennis_atp_")]
        return events_for_keys(provider, keys, "tennis", start, end)
    if competition == "tennis_wta_active":
        keys = [k for k in provider.active_sport_keys("tennis") if k.startswith("tennis_wta_")]
        return events_for_keys(provider, keys, "tennis", start, end)
    sport = "nba" if competition == "basketball_nba" else "tennis" if competition.startswith("tennis_") else "football"
    return events_for_keys(provider, [competition], sport, start, end)


def event_card(event, analysis):
    return (
        f"{competition_flag(event)} {competition_label(event)}\n"
        f"{event.home} vs {event.away}\n\n"
        f"{analysis.strip()}\n\n"
        "💡 Preanálisis: esta capa decide si vale la pena gastar créditos.\n"
        "👇 Tú autorizas el siguiente nivel."
    )


def send_events(sender, events, title):
    events = sorted({e.id: e for e in events}.values(), key=lambda e: e.start_time)
    if not events:
        sender.send(f"{title}\n\nNo encontré partidos en ese periodo.", menu_keyboard())
        return
    # We deliberately cap the AI preanalysis. The user asked to inspect before spending odds credits.
    candidates = events[:10]
    sender.send(
        f"{title}\n\nEncontré {len(events)} partidos.\n"
        "🧠 Ahora estoy haciendo el preanálisis cualitativo; todavía no consulto mercados especializados.",
        menu_keyboard(),
    )
    analyses = generate_preanalysis(candidates, max_events=min(6, len(candidates)))
    if not analyses:
        sender.send("⚪ El preanálisis no encontró partidos suficientemente interesantes para pasar a la siguiente capa.", menu_keyboard())
        return
    for event in candidates:
        analysis = analyses.get(event.id)
        if analysis:
            sender.send(event_card(event, analysis), deep_button(event))
    sender.send("📌 Cuando veas un partido que te interese, pulsa 🔬 Analizar a fondo. Ese es el momento en que autorizas el consumo de créditos.", menu_keyboard())


def process_callback(sender, update):
    cb = update.get("callback_query") or {}
    callback_id = str(cb.get("id", ""))
    message = cb.get("message") or {}
    chat_id = str((message.get("chat") or {}).get("id", ""))
    if chat_id != str(sender.chat_id):
        sender.answer_callback(callback_id, "Chat no autorizado.", True)
        return
    data = str(cb.get("data", ""))
    parts = data.split("|")
    sender.answer_callback(callback_id, "Procesando…")

    if parts[0] == "menu":
        send_menu(sender)
        return
    if parts[0] == "country" and len(parts) == 2 and parts[1] in COUNTRY_CODES:
        name = COUNTRY_CODES[parts[1]]
        sender.send(f"{name}\n\nSelecciona la competencia que quieres revisar:", country_keyboard(parts[1]))
        return
    if parts[0] == "tennis":
        sender.send("🎾 TENIS\n\nSelecciona qué circuito quieres revisar:", tennis_keyboard())
        return
    if parts[0] == "competition" and len(parts) == 2:
        sender.send(f"🏟️ {parts[1].replace('_', ' ').title()}\n\n¿Quieres ver hoy o mañana?", period_keyboard(parts[1]))
        return
    if parts[0] == "league" and len(parts) == 3:
        provider = TheOddsAPIProvider()
        events = fetch_competition_events(provider, parts[1], parts[2])
        send_events(sender, events, f"📊 {competition_label(events[0]) if events else parts[1]} — {'HOY' if parts[2] == 'today' else 'MAÑANA'}")
        return
    if parts[0] == "day" and len(parts) == 2:
        provider = TheOddsAPIProvider()
        start, end = event_window(parts[1])
        events = []
        for sport in DEFAULT_CONFIG.watchlist.sports:
            events.extend(provider.upcoming_events(sport, start, end))
        send_events(sender, events, "📅 AGENDA COMPLETA")
        return
    if parts[0] == "live":
        provider = TheOddsAPIProvider()
        now = datetime.now(timezone.utc)
        events = []
        for sport in DEFAULT_CONFIG.watchlist.sports:
            events.extend(provider.live_events(sport, now=now))
        send_events(sender, events, "🔴 EVENTOS EN VIVO")
        return
    if parts[0] == "track" and len(parts) == 2:
        ok, result = register_offer(parts[1])
        sender.answer_callback(callback_id, result, not ok)
        sender.send(("🟢 " if ok else "🟡 ") + result)
        return
    if parts[0] == "deep" and len(parts) == 3:
        sender.send("⏳ Análisis profundo iniciado. Esta acción sí consume créditos de Odds API.")
        provider = TheOddsAPIProvider()
        event = provider.event_by_id(parts[2], parts[1])
        if event is None:
            sender.send("❌ El evento ya no está disponible.", menu_keyboard())
            return
        scanner = Scanner(provider, DEFAULT_CONFIG)
        candidates = scanner.explore_event(event, max_results=12)
        if not candidates:
            sender.send("⚪ No encontré una señal suficientemente estable después de revisar los mercados disponibles.", menu_keyboard())
            return
        for index, candidate in enumerate(candidates[:8], 1):
            quote = candidate.quote
            line = f" {quote.line:g}" if quote.line is not None else ""
            prediction_id = offer_candidate(candidate)
            marker = "🟢" if candidate.confidence >= 75 else "🟡"
            sender.send(
                f"{marker} #{index} {quote.market}{line}\n"
                f"🎯 {quote.selection}\n"
                f"Probabilidad estimada: {candidate.model_probability:.1%}\n"
                f"Confianza: {candidate.confidence:.0f}/100\n"
                f"Cuota: {quote.odds:.2f}\n"
                f"Ventaja: {candidate.edge:+.1%}\n"
                f"EV: {candidate.expected_value:+.1%}",
                track_button(prediction_id),
            )
        return


def process_message(sender, update):
    message = update.get("message") or {}
    if str((message.get("chat") or {}).get("id", "")) != str(sender.chat_id):
        return
    text = str(message.get("text", "")).strip().lower()
    if text in {"/start", "/menu", "/help", "/ayuda", "📋 menú"}:
        send_menu(sender, intro=False)
    elif text in {"/manana", "🌅 mañana"}:
        provider = TheOddsAPIProvider()
        start, end = event_window("tomorrow")
        events = []
        for sport in DEFAULT_CONFIG.watchlist.sports:
            events.extend(provider.upcoming_events(sport, start, end))
        send_events(sender, events, "🌅 AGENDA DE MAÑANA")
    elif text in {"/hoy", "📅 hoy"}:
        provider = TheOddsAPIProvider()
        start, end = event_window("today")
        events = []
        for sport in DEFAULT_CONFIG.watchlist.sports:
            events.extend(provider.upcoming_events(sport, start, end))
        send_events(sender, events, "📅 AGENDA DE HOY")
    elif text in {"/vivo", "🔴 en vivo"}:
        process_callback(sender, {"callback_query": {"id": "text-live", "message": message, "data": "live|root"}})
    else:
        sender.send("❓ Usa /menu para abrir el panel de control.", menu_keyboard())


def main():
    sender = TelegramAlertSender()
    if not sender.enabled:
        raise SystemExit("Telegram no está configurado.")
    # Polling and not webhook: GitHub Actions cannot host a persistent Telegram webhook.
    sender.delete_webhook(False)
    offset = load_offset()
    deadline = time.monotonic() + int(os.getenv("TELEGRAM_POLL_SECONDS", "255"))
    while time.monotonic() < deadline:
        try:
            updates = sender.get_updates(offset=offset, limit=100, timeout=20)
            for update in updates:
                try:
                    if update.get("callback_query"):
                        process_callback(sender, update)
                    elif update.get("message"):
                        process_message(sender, update)
                except Exception as exc:
                    print(f"Error procesando update: {exc}")
                offset = int(update.get("update_id", 0)) + 1
            if updates and offset is not None:
                save_offset(offset)
        except Exception as exc:
            print(f"Error de polling Telegram: {exc}")
            time.sleep(3)


if __name__ == "__main__":
    main()
