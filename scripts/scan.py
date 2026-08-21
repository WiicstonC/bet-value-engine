import argparse

from app.alerts.manager import AlertManager, alert_due
from app.alerts.telegram import TelegramAlertSender
from app.config import DEFAULT_CONFIG
from app.engine.scanner import Scanner
from app.providers.odds_api import TheOddsAPIProvider


def main() -> None:
    parser = argparse.ArgumentParser(description="Bet Value Scanner")
    parser.add_argument(
        "--full",
        action="store_true",
        help="Analiza toda la ventana configurada en lugar de solo ventanas de alerta.",
    )
    args = parser.parse_args()

    provider = TheOddsAPIProvider()
    scanner = Scanner(provider, DEFAULT_CONFIG)
    alert_only = not args.full

    print("=== BET VALUE SCANNER ===")
    print(f"Modo: {'ALERTA' if alert_only else 'ANÁLISIS COMPLETO'}")
    print(f"Sports: {', '.join(DEFAULT_CONFIG.watchlist.sports)}")
    print(f"Ventana: {DEFAULT_CONFIG.watch_hours}h")
    print(f"Mercados base: {', '.join(DEFAULT_CONFIG.watchlist.markets)}")
    print(f"Bookmaker objetivo: {', '.join(DEFAULT_CONFIG.watchlist.bookmakers)}")
    print(
        "Mercados especializados: descubrimiento por evento + selección por deporte "
        f"(máx {DEFAULT_CONFIG.deep_scan.max_markets_per_event}/evento)"
    )

    candidates = scanner.scan(
        hours=DEFAULT_CONFIG.watch_hours,
        alert_only=alert_only,
    )
    print(f"Candidatos con valor encontrados: {len(candidates)}")

    for index, candidate in enumerate(candidates[:10], start=1):
        print(
            f"#{index} {candidate.event.home} vs {candidate.event.away} | "
            f"{candidate.quote.market} {candidate.quote.selection} @ {candidate.quote.odds:.2f} | "
            f"conf={candidate.confidence:.1f} edge={candidate.edge:.2%} "
            f"ev={candidate.expected_value:.2%} books={candidate.consensus_bookmakers}"
        )

    print(f"Deep events considerados: {scanner.deep_events_considered}")
    print(f"Deep events con mercados: {scanner.deep_events_with_markets}")
    print(f"Mercados especializados solicitados: {scanner.deep_markets_requested}")
    print(f"Cuotas especializadas recibidas: {scanner.deep_quotes_received}")
    if scanner.deep_market_hits:
        market_mix = ", ".join(
            f"{market}={count}" for market, count in scanner.deep_market_hits.most_common()
        )
        print(f"Mercados especializados detectados: {market_mix}")

    if provider.last_quota_remaining is not None:
        print(f"Odds API credits restantes: {provider.last_quota_remaining}")
    if provider.last_quota_used is not None:
        print(f"Odds API credits usados: {provider.last_quota_used}")
    if provider.last_quota_last is not None:
        print(f"Costo de la última consulta de cuotas: {provider.last_quota_last}")

    due = [
        candidate
        for candidate in candidates
        if alert_due(
            candidate,
            DEFAULT_CONFIG.alerts,
            DEFAULT_CONFIG.scan_interval_minutes,
        )
    ]
    print(f"Candidatos dentro de ventana de alerta: {len(due)}")

    manager = AlertManager(TelegramAlertSender(), DEFAULT_CONFIG)
    sent = manager.notify(candidates) if DEFAULT_CONFIG.alerts.enabled else 0
    print(f"Alertas enviadas: {sent}")

    if not candidates:
        print("Sin señal: el motor no encontró una oportunidad que supere todos los filtros.")
    elif not due:
        print("Hay oportunidades, pero ninguna está en una ventana de alerta ahora.")


if __name__ == "__main__":
    main()
