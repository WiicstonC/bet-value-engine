from app.alerts.manager import AlertManager
from app.alerts.telegram import TelegramAlertSender
from app.config import DEFAULT_CONFIG
from app.engine.scanner import Scanner
from app.providers.odds_api import TheOddsAPIProvider


def main() -> None:
    provider = TheOddsAPIProvider()
    scanner = Scanner(provider, DEFAULT_CONFIG)
    candidates = scanner.scan(hours=48)

    print(f"Eventos con value: {len(candidates)}")

    manager = AlertManager(TelegramAlertSender())
    sent = manager.notify(candidates) if DEFAULT_CONFIG.alerts.enabled else 0
    print(f"Alertas enviadas: {sent}")


if __name__ == "__main__":
    main()
