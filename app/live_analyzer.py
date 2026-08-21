from app.config import EngineConfig
from app.engine.market_catalog import select_deep_markets
from app.engine.scanner import Scanner
from app.models import Event, LiveIncident
from app.providers.odds_api import TheOddsAPIProvider


def analyze_after_incident(
    provider: TheOddsAPIProvider,
    scanner: Scanner,
    event: Event,
    incident: LiveIncident,
    config: EngineConfig,
):
    available = provider.available_markets(event)
    all_available = set().union(*available.values()) if available else set()

    preferred = select_deep_markets(event.sport, all_available)
    if incident.kind == "red_card" and event.sport == "football":
        priority = ["h2h", "spreads", "totals", "alternate_totals", "alternate_totals_corners", "alternate_totals_cards"]
        preferred = [market for market in priority if market in all_available] + preferred
    elif incident.kind in {"goal", "penalty"} and event.sport == "football":
        priority = ["totals", "h2h", "spreads", "alternate_totals_corners", "alternate_totals_cards"]
        preferred = [market for market in priority if market in all_available] + preferred
    elif incident.kind in {"injury", "ejection", "technical_foul"} and event.sport == "nba":
        priority = ["player_points", "player_rebounds", "player_assists", "player_threes", "player_points_rebounds_assists", "spreads", "totals"]
        preferred = [market for market in priority if market in all_available] + preferred

    markets = list(dict.fromkeys(preferred))[: config.deep_scan.max_markets_per_event]
    if not markets:
        return []

    quotes = provider.event_quotes(event, markets)
    results = []
    for target in config.watchlist.bookmakers:
        results.extend(
            scanner._evaluate_quotes(
                event,
                quotes,
                target,
                minimum_confidence=config.live.minimum_confidence,
                minimum_edge=config.live.minimum_edge,
                minimum_expected_value=config.live.minimum_expected_value,
            )
        )
    unique = {}
    for candidate in results:
        key = (candidate.event.id, candidate.quote.market, candidate.quote.selection, candidate.quote.line, candidate.quote.bookmaker)
        old = unique.get(key)
        if old is None or candidate.confidence > old.confidence:
            unique[key] = candidate
    result = list(unique.values())
    result.sort(key=lambda c: (c.confidence, c.edge, c.expected_value), reverse=True)
    return result[: config.live.max_alerts_per_run]
