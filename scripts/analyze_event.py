import argparse

from app.alerts.manager import format_candidate
from app.config import DEFAULT_CONFIG
from app.engine.scanner import Scanner
from app.providers.odds_api import TheOddsAPIProvider


def main() -> None:
    parser = argparse.ArgumentParser(description="Deep analysis of one selected event")
    parser.add_argument("--sport", required=True, choices=["tennis", "football", "nba"])
    parser.add_argument("--event-id", required=True)
    args = parser.parse_args()

    config = DEFAULT_CONFIG
    provider = TheOddsAPIProvider()
    event = provider.event_by_id(args.event_id, args.sport)
    if event is None:
        raise SystemExit(f"No se encontró el evento {args.event_id} en {args.sport}.")

    scanner = Scanner(provider, config)
    candidates = scanner.analyze_event(event)

    print("=== BET VALUE MANUAL DEEP ANALYSIS ===")
    print(f"Evento: {event.home} vs {event.away}")
    print(f"Sport: {event.sport}")
    print(f"Event ID: {event.id}")
    print(f"Candidatos con valor: {len(candidates)}")
    print(f"Mercados especializados solicitados: {scanner.deep_markets_requested}")
    print(f"Cuotas especializadas recibidas: {scanner.deep_quotes_received}")
    if provider.last_quota_remaining is not None:
        print(f"Odds API credits restantes: {provider.last_quota_remaining}")
    if provider.last_quota_used is not None:
        print(f"Odds API credits usados: {provider.last_quota_used}")
    if provider.last_quota_last is not None:
        print(f"Costo de la última consulta: {provider.last_quota_last}")

    for index, candidate in enumerate(candidates, start=1):
        print(f"\n--- OPCIÓN #{index} ---")
        print(format_candidate(candidate, config.timezone))

    if not candidates:
        print("Sin señal que supere los filtros actuales. No significa que el partido no tenga mercados interesantes; significa que el modelo actual no encontró suficiente consenso/edge.")


if __name__ == "__main__":
    main()
