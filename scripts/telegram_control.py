import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from app.alerts.manager import competition_flag, competition_label
from app.alerts.telegram import TelegramAlertSender
from app.analysis.preanalysis import generate_preanalysis
from app.config import DEFAULT_CONFIG
from app.engine.scanner import Scanner
from app.providers.odds_api import TheOddsAPIProvider

STATE_PATH = Path(__file__).resolve().parent.parent / "data" / "telegram_offset.json"


def _load_offset() -> int | None:
    if not STATE_PATH.exists():
        return None
    try:
        return int(json.loads(STATE_PATH.read_text(encoding="utf-8")).get("offset"))
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def _save_offset(offset: int) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps({"offset": offset}, indent=2), encoding="utf-8")


def _safe_callback_answer(sender: TelegramAlertSender, callback_id: str, text: str, show_alert: bool = False) -> None:
    try:
        sender.answer_callback(callback_id, text, show_alert=show_alert)
    except Exception as exc:
        print(f"Callback answer no disponible: {exc}")


def _button(sport: str, event_id: str) -> dict:
    return {"inline_keyboard": [[{"text": "🔬 Analizar a fondo", "callback_data": f"deep|{sport}|{event_id}"}]]}


def _event_card(event, preanalysis: str) -> str:
    local = event.start_time.astimezone(ZoneInfo(DEFAULT_CONFIG.timezone)).strftime("%d/%m %H:%M")
    return (
        f"{competition_flag(event)} {competition_label(event)}\n"
        f"{event.sport.upper()} | {event.home} vs {event.away}\n"
        f"🕒 {local} Colombia\n\n"
        f"{preanalysis}\n\n"
        "💳 La consulta profunda se hará solo si pulsas el botón."
    )


def _send_event_cards(sender: TelegramAlertSender, events, title: str) -> int:
    if not events:
        sender.send(f"{title}\n\nNo encontré eventos en la ventana solicitada.")
        return 0
    pre = generate_preanalysis(events, max_events=min(8, len(events)))
    sent = sender.send(f"{title}\n\nEventos encontrados: {len(events)}\nCuotas/mercados especializados consultados: 0")
    for event in events:
        analysis = pre.get(event.id)
        if not analysis:
            continue
        sent += int(sender.send(_event_card(event, analysis), _button(event.sport, event.id)))
    return sent


def _fetch_window(day_offset: int = 0, first_hours: int | None = None, max_per_sport: int = 4):
    provider = TheOddsAPIProvider()
    tz = ZoneInfo(DEFAULT_CONFIG.timezone)
    now = datetime.now(tz)
    target = (now + timedelta(days=day_offset)).date()
    start_local = datetime.combine(target, datetime.min.time(), tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    if first_hours is not None:
        end_local = min(end_local, start_local + timedelta(hours=first_hours))
    start = start_local.astimezone(timezone.utc)
    end = end_local.astimezone(timezone.utc)
    events = []
    for sport in DEFAULT_CONFIG.watchlist.sports:
        found = provider.upcoming_events(sport, start, end)
        events.extend(found[:max_per_sport])
    unique = {e.id: e for e in events}
    return provider, sorted(unique.values(), key=lambda e: e.start_time)


def _handle_command(sender: TelegramAlertSender, text: str) -> None:
    command = text.strip().split()[0].lower().split("@")[0]
    if command in {"/start", "/menu", "/ayuda", "/help"}:
        sender.send(
            "🤖 BET VALUE ENGINE\n\n"
            "Desde ahora Telegram es el centro de control.\n\n"
            "📅 /agenda — agenda de hoy + preanálisis\n"
            "🌅 /manana — primeros partidos de mañana\n"
            "🔴 /vivo — eventos que están en vivo\n"
            "💳 /estado — estado de las claves configuradas\n\n"
            "🔬 Cada botón Analizar a fondo autoriza el consumo de Odds API."
        )
        return
    if command == "/agenda":
        _, events = _fetch_window(day_offset=0, max_per_sport=8)
        _send_event_cards(sender, events, "📅 AGENDA DE HOY + PREANÁLISIS")
        return
    if command == "/manana":
        _, events = _fetch_window(day_offset=1, first_hours=12, max_per_sport=5)
        _send_event_cards(sender, events, "🌅 PRIMEROS PARTIDOS DE MAÑANA + PREANÁLISIS")
        return
    if command == "/vivo":
        provider = TheOddsAPIProvider()
        now = datetime.now(timezone.utc)
        events = []
        for sport in DEFAULT_CONFIG.watchlist.sports:
            events.extend(provider.live_events(sport, now=now))
        unique = {e.id: e for e in events}
        events = sorted(unique.values(), key=lambda e: e.start_time)
        if not events:
            sender.send("🔴 EN VIVO\n\nNo encontré eventos en vivo ahora mismo.")
        else:
            sender.send("🔴 EN VIVO\n\n" + "\n".join(f"{competition_flag(e)} {e.home} vs {e.away}" for e in events[:20]))
        return
    if command == "/estado":
        configured = [name for name in ("ODDS_API_KEY", "ODDS_API_KEY_2", "ODDS_API_KEY_3") if __import__("os").getenv(name)]
        sender.send("💳 ESTADO\n\n" + "\n".join(f"✅ {name}" for name in configured) + f"\n\nClaves configuradas: {len(configured)}\n\nLas cuotas solo se consultan al solicitar análisis profundo.")
        return
    sender.send("❓ Comando no reconocido. Usa /menu para ver las opciones.")


def _format_deep_result(event, candidates, scanner, provider) -> str:
    header = f"🔬 ANÁLISIS PROFUNDO\n\n{competition_flag(event)} {competition_label(event)}\n{event.sport.upper()} | {event.home} vs {event.away}\n\n"
    if not candidates:
        body = "⚪ No apareció una selección con consenso suficiente entre casas independientes.\n\nEsto NO significa que no existan mercados interesantes; significa que el motor no tiene todavía suficiente consenso externo para valorar una cuota con confianza."
    else:
        lines = ["🏆 MERCADOS MÁS INTERESANTES", ""]
        for index, candidate in enumerate(candidates[:8], start=1):
            quote = candidate.quote
            line = f" {quote.line:g}" if quote.line is not None else ""
            marker = "🟢" if candidate.edge >= 0.05 else "🟡" if candidate.edge >= 0 else "🔴"
            lines.extend([f"{marker} #{index} {quote.market}{line}", f"   {quote.selection} @ {quote.odds:.2f} Betano", f"   Consenso: {candidate.model_probability:.1%} | Implícita: {candidate.implied_probability:.1%}", f"   Edge: {candidate.edge:+.1%} | EV: {candidate.expected_value:+.1%} | Conf.: {candidate.confidence:.0f}/100", f"   Casas independientes: {candidate.consensus_bookmakers}", ""])
        body = "\n".join(lines).rstrip()
    markets = ", ".join(scanner.deep_market_hits.keys()) or "ninguno"
    quota = f"\n💳 Créditos restantes: {provider.last_quota_remaining}" if provider.last_quota_remaining is not None else ""
    return header + body + f"\n\n📊 Mercados consultados: {markets}\n📦 Cuotas recibidas: {scanner.deep_quotes_received}{quota}\n\n⚠️ Análisis estadístico; no garantiza resultados."


def _process_callback(sender: TelegramAlertSender, update: dict) -> None:
    callback = update.get("callback_query") or {}
    callback_id = str(callback.get("id", ""))
    message = callback.get("message") or {}
    chat_id = str((message.get("chat") or {}).get("id", ""))
    if not callback_id or chat_id != str(sender.chat_id):
        _safe_callback_answer(sender, callback_id, "No autorizado.", True)
        return
    parts = str(callback.get("data", "")).split("|", 2)
    if len(parts) != 3 or parts[0] != "deep":
        _safe_callback_answer(sender, callback_id, "Acción no reconocida.", True)
        return
    sport, event_id = parts[1], parts[2]
    if sport not in DEFAULT_CONFIG.watchlist.sports:
        _safe_callback_answer(sender, callback_id, "Deporte no habilitado.", True)
        return
    _safe_callback_answer(sender, callback_id, "Solicitud recibida. Consultando mercados…")
    if message.get("message_id"):
        try:
            sender.edit_reply_markup(chat_id, int(message["message_id"]))
        except Exception as exc:
            print(f"No se pudo retirar botón: {exc}")
    sender.send("⏳ Consulta profunda iniciada. Esta acción sí consume créditos de Odds API.")
    provider = TheOddsAPIProvider()
    event = provider.event_by_id(event_id, sport)
    if event is None:
        sender.send("❌ No pude recuperar ese evento; puede haber expirado.")
        return
    scanner = Scanner(provider, DEFAULT_CONFIG)
    candidates = scanner.explore_event(event, max_results=12)
    sender.send(_format_deep_result(event, candidates, scanner, provider))


def main() -> None:
    sender = TelegramAlertSender()
    if not sender.enabled:
        raise SystemExit("Telegram no está configurado.")
    try:
        sender.delete_webhook(False)
    except Exception as exc:
        print(f"Webhook no disponible: {exc}")
    offset = _load_offset()
    updates = sender.get_updates(offset=offset, limit=50, timeout=0)
    print(f"Telegram updates recibidos: {len(updates)}")
    next_offset = offset
    for update in updates:
        update_id = int(update.get("update_id", 0))
        try:
            message = update.get("message") or {}
            chat_id = str((message.get("chat") or {}).get("id", ""))
            if chat_id == str(sender.chat_id) and str(message.get("text", "")).startswith("/"):
                _handle_command(sender, str(message["text"]))
            elif update.get("callback_query"):
                _process_callback(sender, update)
        except Exception as exc:
            print(f"Error procesando update {update_id}: {exc}")
        next_offset = max(next_offset or 0, update_id + 1)
    if next_offset is not None and next_offset != offset:
        _save_offset(next_offset)
        print(f"Telegram offset actualizado: {next_offset}")


if __name__ == "__main__":
    main()
