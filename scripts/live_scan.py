from app.alerts.manager import AlertManager
from app.alerts.telegram import TelegramAlertSender
from app.config import DEFAULT_CONFIG
from app.engine.scanner import Scanner
from app.live_state import LiveState
from app.providers.odds_api import TheOddsAPIProvider


def main() -> None:
    config = DEFAULT_CONFIG
    provider = TheOddsAPIProvider()
    scanner = Scanner(provider, config)
    state = LiveState()

    candidates = scanner.scan_live()
    alerts = []
    for candidate in candidates:
        should_alert, shock = state.update_candidate(
            candidate,
            shock_percent=config.live.price_shock_percent,
        )
        if should_alert:
            alerts.append((candidate, shock))

    state.save()

    print("=== BET VALUE LIVE SCANNER ===")
    print(f"Sports: {', '.join(config.watchlist.sports)}")
    print(f"Live candidates: {len(candidates)}")
    print(f"Live alerts: {len(alerts)}")
    print(f"API key activa: {provider.active_key_number}")
    print(f"Failover de API keys: {provider.failover_count}")
    if provider.last_quota_remaining is not None:
        print(f"Odds API credits restantes: {provider.last_quota_remaining}")
    if provider.last_quota_used is not None:
        print(f"Odds API credits usados: {provider.last_quota_used}")
    if provider.last_quota_last is not None:
        print(f"Costo de la última consulta: {provider.last_quota_last}")

    manager = AlertManager(TelegramAlertSender(), config)
    sent = manager.notify_live([candidate for candidate, _ in alerts]) if config.live.enabled else 0
    print(f"Alertas Telegram enviadas: {sent}")

    for candidate, shock in alerts:
        shock_text = "primera señal" if shock is None else f"cambio cuota {shock:.1f}%"
        print(
            f"🚨 {candidate.event.home} vs {candidate.event.away} | "
            f"{candidate.quote.market} {candidate.quote.selection} @ {candidate.quote.odds:.2f} | {shock_text}"
        )


if __name__ == "__main__":
    main()
