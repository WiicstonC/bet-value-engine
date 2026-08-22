from datetime import datetime, timedelta, timezone

from app.alerts.telegram import TelegramAlertSender
from app.config import DEFAULT_CONFIG
from scripts.telegram_control import _fetch_window, _send_event_cards


def main() -> None:
    sender = TelegramAlertSender()
    if not sender.enabled:
        raise SystemExit("Telegram no está configurado.")
    _, events = _fetch_window(day_offset=1, first_hours=14, max_per_sport=8)
    _send_event_cards(sender, events, "🌅 AGENDA AUTOMÁTICA — PRIMEROS PARTIDOS DE MAÑANA")
    print(f"Eventos enviados: {len(events)}")
    print(f"Hora UTC: {datetime.now(timezone.utc).isoformat()}")


if __name__ == "__main__":
    main()
