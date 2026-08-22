import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from app.alerts.manager import competition_flag, competition_label
from app.alerts.telegram import TelegramAlertSender
from app.analysis.preanalysis import generate_preanalysis
from app.config import DEFAULT_CONFIG
from app.engine.scanner import Scanner
from app.learning.ledger import offer_candidate, register_offer, stats as learning_stats
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


def _menu_keyboard() -> dict:
    return {
        "keyboard": [
            [{"text": "🌅 Mañana"}, {"text": "📅 Agenda"}],
            [{"text": "🔴 En vivo"}, {"text": "🧠 Aprendizaje"}],
            [{"text": "⏳ Pendientes"}, {"text": "💳 Estado"}],
        ],
        "resize_keyboard": True,
        "is_persistent": True,
    }


def _button(sport: str, event_id: str) -> dict:
    return {"inline_keyboard": [[{"text": "🔬 Analizar a fondo", "callback_data": f"deep|{sport}|{event_id}"}]]}


def _track_button(prediction_id: str) -> dict:
    return {"inline_keyboard": [[{"text": "🎯 Seguir este pronóstico", "callback_data": f"track|{prediction_id}"}]]}


def _event_card(event, preanalysis: str) -> str:
    local = event.start_time.astimezone(ZoneInfo(DEFAULT_CONFIG.timezone)).strftime("%d/%m %H:%M")
    return (
        f"{competition_flag(event)} {competition_label(event)}\n"
        f"{event.sport.upper()} | {event.home} vs {event.away}\n"
        f"🕒 {local} Colombia\n\n"
        f"{preanalysis}\n\n"
        "💳 Los mercados y cuotas solo se consultan si pulsas 🔬 Analizar a fondo."
    )


def _send_event_cards(sender: TelegramAlertSender, events, title: str) -> int:
    if not events:
        sender.send(f"{title}\n\nNo encontré eventos en la ventana solicitada.")
        return 0
    pre = generate_preanalysis(events, max_events=min(12, len(events)))
    sent = sender.send(
        f"{title}\n\nEventos encontrados: {len(events)}\n"
        "🧠 Fase 1: preanálisis y búsqueda del mercado potencial.\n"
        "💳 Fase 2: solo gastamos créditos cuando tú pulsas 🔬.\n\n"
        "No buscamos únicamente ganador: el objetivo es encontrar el mercado con mayor probabilidad."
    )
    for event in events:
        analysis = pre.get(event.id)
        if not analysis:
            continue
        sent += int(sender.send(_event_card(event, analysis), _button(event.sport, event.id)))
    return sent


def _fetch_window(day_offset: int = 0, first_hours: int | None = None, max_per_sport: int = 6):
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


def _send_learning_stats(sender: TelegramAlertSender) -> None:
    data = learning_stats()
    hit = f"{data['hit_rate']:.1%}" if data["hit_rate"] is not None else "—"
    lines = [
        "🧠 BET VALUE ENGINE — APRENDIZAJE",
        "",
        f"Predicciones registradas: {data['total']}",
        f"Pendientes: {data['pending']}",
        f"Resueltas: {data['resolved']}",
        f"Aciertos: {data['wins']}",
        f"Fallos: {data['losses']}",
        f"Hit rate observado: {hit}",
        "",
        "📐 CALIBRACIÓN",
    ]
    for bucket in data["calibration"]:
        lines.append(f"{bucket['range']}: pred. {bucket['predicted']:.1%} → real {bucket['actual']:.1%} ({bucket['count']})")
    if not data["calibration"]:
        lines.append("Todavía necesitamos resultados reales para calibrar el modelo.")
    lines.extend(["", "El motor guardará cada probabilidad y comparará su predicción con el resultado real."])
    sender.send("\n".join(lines), _menu_keyboard())


def _send_pending(sender: TelegramAlertSender) -> None:
    from app.learning.ledger import pending
    rows = pending()
    if not rows:
        sender.send("⏳ PREDICCIONES PENDIENTES\n\nNo hay pronósticos registrados esperando resultado.", _menu_keyboard())
        return
    lines = ["⏳ PREDICCIONES PENDIENTES", ""]
    for row in rows[:20]:
        local = datetime.fromisoformat(row["start_time"]).astimezone(ZoneInfo(DEFAULT_CONFIG.timezone)).strftime("%d/%m %H:%M")
        lines.extend([
            f"🎯 {row['home']} vs {row['away']}",
            f"{row['market']} | {row['selection']} {row['line'] if row['line'] is not None else ''}",
            f"Probabilidad: {float(row['model_probability']):.1%} | Cuota: {float(row['odds']):.2f}",
            f"Inicio: {local}",
            "",
        ])
    sender.send("\n".join(lines).rstrip(), _menu_keyboard())


def _handle_command(sender: TelegramAlertSender, text: str) -> None:
    normalized = text.strip().lower()
    aliases = {
        "🌅 mañana": "/manana",
        "📅 agenda": "/agenda",
        "🔴 en vivo": "/vivo",
        "🧠 aprendizaje": "/aprendizaje",
        "⏳ pendientes": "/pendientes",
        "💳 estado": "/estado",
    }
    normalized = aliases.get(normalized, normalized)
    command = normalized.split()[0].split("@")[0]
    if command in {"/start", "/menu", "/ayuda", "/help"}:
        sender.send(
            "🤖 BET VALUE ENGINE\n\n"
            "Telegram es el centro de control.\n\n"
            "🌅 /manana — primeros partidos de mañana\n"
            "📅 /agenda — agenda de hoy + preanálisis\n"
            "🔴 /vivo — eventos en vivo\n"
            "🧠 /aprendizaje — resultados y calibración\n"
            "⏳ /pendientes — pronósticos en seguimiento\n"
            "💳 /estado — estado de las claves\n\n"
            "🔬 Cada botón de análisis autoriza una consulta profunda.\n"
            "🎯 El botón de seguimiento guarda el pronóstico para que el sistema aprenda del resultado.\n\n"
            "⚠️ El motor registra y evalúa pronósticos; no realiza apuestas reales automáticamente.",
            _menu_keyboard(),
        )
        return
    if command == "/agenda":
        _, events = _fetch_window(day_offset=0, max_per_sport=8)
        _send_event_cards(sender, events, "📅 AGENDA DE HOY + PREANÁLISIS")
        return
    if command == "/manana":
        _, events = _fetch_window(day_offset=1, first_hours=14, max_per_sport=8)
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
            sender.send("🔴 EN VIVO\n\nNo encontré eventos en vivo ahora mismo.", _menu_keyboard())
        else:
            sender.send("🔴 EN VIVO\n\n" + "\n".join(f"{competition_flag(e)} {e.home} vs {e.away}" for e in events[:20]), _menu_keyboard())
        return
    if command == "/aprendizaje":
        _send_learning_stats(sender)
        return
    if command == "/pendientes":
        _send_pending(sender)
        return
    if command == "/estado":
        configured = [name for name in ("ODDS_API_KEY", "ODDS_API_KEY_2", "ODDS_API_KEY_3") if os.getenv(name)]
        sender.send(
            "💳 ESTADO\n\n"
            + "\n".join(f"✅ {name}" for name in configured)
            + f"\n\nClaves configuradas: {len(configured)}\n"
            "\nLas cuotas especializadas solo se consultan al solicitar análisis profundo.",
            _menu_keyboard(),
        )
        return
    sender.send("❓ Comando no reconocido. Pulsa /menu para mostrar el control.", _menu_keyboard())


def _deep_messages(event, candidates, scanner, provider) -> list[tuple[str, dict | None]]:
    header = (
        f"🔬 ANÁLISIS PROFUNDO\n\n"
        f"{competition_flag(event)} {competition_label(event)}\n"
        f"{event.sport.upper()} | {event.home} vs {event.away}\n\n"
        "🎯 PRIORIDAD: PROBABILIDAD ESTIMADA\n"
        "La cuota se usa para medir valor; no es el objetivo del modelo."
    )
    messages: list[tuple[str, dict | None]] = [(header, None)]
    if not candidates:
        messages.append((
            "⚪ No apareció una selección con consenso suficiente entre casas independientes.\n\n"
            "El partido no queda descartado para siempre: simplemente no hay una señal suficientemente estable con los datos consultados.",
            None,
        ))
        return messages
    for index, candidate in enumerate(candidates[:8], start=1):
        quote = candidate.quote
        line = f" {quote.line:g}" if quote.line is not None else ""
        marker = "🟢" if candidate.confidence >= 75 and candidate.edge >= 0.05 else "🟡" if candidate.confidence >= 60 else "🔴"
        prediction_id = offer_candidate(candidate)
        text = "\n".join([
            f"{marker} #{index} {quote.market}{line}",
            f"🎯 {quote.selection}",
            f"Probabilidad estimada: {candidate.model_probability:.1%}",
            f"Confianza: {candidate.confidence:.0f}/100",
            f"Cuota Betano: {quote.odds:.2f}",
            f"Ventaja: {candidate.edge:+.1%} | EV: {candidate.expected_value:+.1%}",
            f"Casas independientes: {candidate.consensus_bookmakers}",
            "",
            "Pulsa el botón solo si quieres guardar este pronóstico para seguimiento y aprendizaje."
        ])
        messages.append((text, _track_button(prediction_id)))
    markets = ", ".join(scanner.deep_market_hits.keys()) or "ninguno"
    quota = f"\n💳 Créditos restantes: {provider.last_quota_remaining}" if provider.last_quota_remaining is not None else ""
    messages.append((f"📊 Mercados consultados: {markets}\n📦 Cuotas recibidas: {scanner.deep_quotes_received}{quota}\n\n⚠️ Probabilidad estimada ≠ garantía de resultado.", None))
    return messages


def _process_callback(sender: TelegramAlertSender, update: dict) -> None:
    callback = update.get("callback_query") or {}
    callback_id = str(callback.get("id", ""))
    message = callback.get("message") or {}
    chat_id = str((message.get("chat") or {}).get("id", ""))
    if not callback_id or chat_id != str(sender.chat_id):
        _safe_callback_answer(sender, callback_id, "No autorizado.", True)
        return
    parts = str(callback.get("data", "")).split("|", 2)
    if len(parts) < 2:
        _safe_callback_answer(sender, callback_id, "Acción no reconocida.", True)
        return
    if parts[0] == "track":
        prediction_id = parts[1]
        ok, result = register_offer(prediction_id)
        _safe_callback_answer(sender, callback_id, result, not ok)
        sender.send(("🟢 " if ok else "🟡 ") + result + "\n\nUsa 🧠 Aprendizaje para ver cómo evoluciona la calibración.", _menu_keyboard())
        return
    if parts[0] != "deep" or len(parts) != 3:
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
        sender.send("❌ No pude recuperar ese evento; puede haber expirado.", _menu_keyboard())
        return
    scanner = Scanner(provider, DEFAULT_CONFIG)
    candidates = scanner.explore_event(event, max_results=12)
    for text, markup in _deep_messages(event, candidates, scanner, provider):
        sender.send(text, markup)


def main() -> None:
    sender = TelegramAlertSender()
    if not sender.enabled:
        raise SystemExit("Telegram no está configurado.")
    try:
        sender.delete_webhook(False)
    except Exception as exc:
        print(f"Webhook no disponible: {exc}")
    offset = _load_offset()
    updates = sender.get_updates(offset=offset, limit=100, timeout=15)
    print(f"Telegram updates recibidos: {len(updates)}")

    if os.getenv("TELEGRAM_HEARTBEAT", "false").lower() == "true" and not updates:
        sender.send(
            "🟢 BET VALUE ENGINE — CONTROL TELEGRAM ACTIVO\n\n"
            "Polling conectado y listo para recibir comandos.\n"
            "Prueba ahora: /menu\n\n"
            "El próximo comando se procesará automáticamente; no necesitas entrar a GitHub."
        )

    next_offset = offset
    for update in updates:
        update_id = int(update.get("update_id", 0))
        try:
            message = update.get("message") or {}
            chat_id = str((message.get("chat") or {}).get("id", ""))
            if chat_id == str(sender.chat_id) and str(message.get("text", "")):
                text = str(message["text"])
                if text.startswith("/") or text in {"🌅 Mañana", "📅 Agenda", "🔴 En vivo", "🧠 Aprendizaje", "⏳ Pendientes", "💳 Estado"}:
                    _handle_command(sender, text)
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
