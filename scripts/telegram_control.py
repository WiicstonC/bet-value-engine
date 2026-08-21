import json
from pathlib import Path

from app.alerts.manager import competition_flag, competition_label
from app.alerts.telegram import TelegramAlertSender
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


def _format_deep_result(event, candidates, scanner, provider) -> str:
    header = (
        f"🔬 ANÁLISIS PROFUNDO\n\n"
        f"{competition_flag(event)} {competition_label(event)}\n"
        f"{event.sport.upper()} | {event.home} vs {event.away}\n\n"
    )

    if not candidates:
        body = (
            "⚪ No apareció una selección con consenso suficiente entre casas independientes.\n\n"
            "Esto NO significa que no existan mercados interesantes: significa que el motor no tiene todavía suficiente consenso externo para valorar una cuota de Betano con confianza."
        )
    else:
        lines = ["🏆 MERCADOS MÁS INTERESANTES", ""]
        for index, candidate in enumerate(candidates[:8], start=1):
            quote = candidate.quote
            line = f" {quote.line:g}" if quote.line is not None else ""
            if candidate.edge >= 0.05:
                marker = "🟢"
            elif candidate.edge >= 0:
                marker = "🟡"
            else:
                marker = "🔴"
            lines.extend([
                f"{marker} #{index} {quote.market}{line}",
                f"   {quote.selection} @ {quote.odds:.2f} Betano",
                f"   Consenso: {candidate.model_probability:.1%} | Implícita: {candidate.implied_probability:.1%}",
                f"   Edge: {candidate.edge:+.1%} | EV: {candidate.expected_value:+.1%} | Conf.: {candidate.confidence:.0f}/100",
                f"   Casas independientes: {candidate.consensus_bookmakers}",
                "",
            ])
        body = "\n".join(lines).rstrip()

    markets = ", ".join(scanner.deep_market_hits.keys()) or "ninguno"
    quota = ""
    if provider.last_quota_remaining is not None:
        quota = f"\n💳 Créditos restantes: {provider.last_quota_remaining}"
    if provider.last_quota_last is not None:
        quota += f" | Última consulta: {provider.last_quota_last}"

    footer = (
        f"\n\n📊 Mercados consultados: {markets}"
        f"\n📦 Cuotas recibidas: {scanner.deep_quotes_received}"
        f"{quota}"
        "\n\n⚠️ El análisis ordena oportunidades estadísticas; no garantiza resultados."
    )
    return header + body + footer


def _process_callback(sender: TelegramAlertSender, update: dict) -> None:
    callback = update.get("callback_query") or {}
    callback_id = str(callback.get("id", ""))
    message = callback.get("message") or {}
    chat = message.get("chat") or {}
    chat_id = str(chat.get("id", ""))

    if not callback_id or chat_id != str(sender.chat_id):
        if callback_id:
            sender.answer_callback(callback_id, "No autorizado.", show_alert=True)
        return

    data = str(callback.get("data", ""))
    parts = data.split("|", 2)
    if len(parts) != 3 or parts[0] != "deep":
        sender.answer_callback(callback_id, "Acción no reconocida.", show_alert=True)
        return

    sport, event_id = parts[1], parts[2]
    if sport not in DEFAULT_CONFIG.watchlist.sports:
        sender.answer_callback(callback_id, "Deporte no habilitado.", show_alert=True)
        return

    sender.answer_callback(callback_id, "Solicitud recibida. Consultando mercados…")
    message_id = message.get("message_id")
    if message_id:
        try:
            sender.edit_reply_markup(chat_id, int(message_id))
        except Exception as exc:
            print(f"No se pudo retirar el botón: {exc}")

    sender.send(
        "⏳ Estoy consultando los mercados especializados de este partido.\n"
        "Esta acción sí consume créditos de Odds API."
    )

    provider = TheOddsAPIProvider()
    event = provider.event_by_id(event_id, sport)
    if event is None:
        sender.send("❌ No pude recuperar ese evento. Puede haber expirado o cambiado en el proveedor.")
        return

    scanner = Scanner(provider, DEFAULT_CONFIG)
    candidates = scanner.explore_event(event, max_results=12)
    sender.send(_format_deep_result(event, candidates, scanner, provider))


def main() -> None:
    sender = TelegramAlertSender()
    if not sender.enabled:
        raise SystemExit("Telegram no está configurado.")

    offset = _load_offset()
    updates = sender.get_updates(offset=offset, limit=50, timeout=0)
    print(f"Telegram updates recibidos: {len(updates)}")

    next_offset = offset
    for update in updates:
        update_id = int(update.get("update_id", 0))
        try:
            if update.get("callback_query"):
                _process_callback(sender, update)
        except Exception as exc:
            print(f"Error procesando update {update_id}: {exc}")
        next_offset = max(next_offset or 0, update_id + 1)

    if next_offset is not None and next_offset != offset:
        _save_offset(next_offset)
        print(f"Telegram offset actualizado: {next_offset}")


if __name__ == "__main__":
    main()
