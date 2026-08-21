from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.alerts.manager import AlertManager
from app.alerts.telegram import TelegramAlertSender
from app.config import DEFAULT_CONFIG
from app.providers.odds_api import TheOddsAPIProvider


def main() -> None:
    config = DEFAULT_CONFIG
    provider = TheOddsAPIProvider()
    local_now = datetime.now(ZoneInfo(config.timezone))
    local_end = (local_now + timedelta(days=config.daily_digest.days_ahead)).replace(hour=0, minute=0, second=0, microsecond=0)
    start = local_now.astimezone(timezone.utc)
    end = local_end.astimezone(timezone.utc)

    events = []
    for sport in config.watchlist.sports:
        events.extend(provider.upcoming_events(sport, start, end))

    unique = {event.id: event for event in events}
    events = sorted(unique.values(), key=lambda event: event.start_time)

    print("=== BET VALUE DAILY DIGEST ===")
    print(f"Sports: {', '.join(config.watchlist.sports)}")
    print(f"Eventos del periodo: {len(events)}")
    print("Odds consultadas: 0")
    print(f"API key activa: {provider.active_key_number}")

    manager = AlertManager(TelegramAlertSender(), config)
    sent = manager.send_daily_digest(events) if config.daily_digest.enabled else 0
    print(f"Mensajes Telegram enviados: {sent}")


if __name__ == "__main__":
    main()
