from datetime import datetime, timezone

from app.alerts.manager import AlertManager
from app.alerts.telegram import TelegramAlertSender
from app.config import DEFAULT_CONFIG
from app.engine.scanner import Scanner
from app.providers.odds_api import TheOddsAPIProvider


def is_alert_window(start_time: datetime, windows: list[int], tolerance: int = 5) -> bool:
    minutes = (start_time - datetime.now(timezone.utc)).total_seconds() / 60
    return any(abs(minutes - target) <= tolerance for target in windows)


def main() -> None:
    provider = TheOddsAPIProvider()
    scanner = Scanner(provider, DEFAULT_CONFIG)
    candidates = scanner.scan(hours=DEFAULT_CONFIG.watch_hours)

    candidates = [
        candidate
        for candidate in candidates
        if is_alert_window(
            candidate.event.start_time,
            DEFAULT_CONFIG.alerts.minutes_before_start,
        )
    ]

    print(f"Candidatos en ventana de alerta: {len(candidates)}")

    manager = AlertManager(TelegramAlertSender(), DEFAULT_CONFIG)
    sent = manager.notify(candidates) if DEFAULT_CONFIG.alerts.enabled else 0
    print(f"Alertas enviadas: {sent}")


if __name__ == "__main__":
    main()
