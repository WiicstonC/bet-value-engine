from app.config import WatchlistConfig
from app.models import Event, MarketQuote


def matches_watchlist(event: Event, config: WatchlistConfig) -> bool:
    if config.sports and event.sport.lower() not in {s.lower() for s in config.sports}:
        return False

    text = f"{event.competition} {event.home} {event.away}".lower()

    if config.competitions and not any(x.lower() in text for x in config.competitions):
        return False

    if config.teams and not any(x.lower() in text for x in config.teams):
        return False

    if config.players and not any(x.lower() in text for x in config.players):
        return False

    return True


def market_allowed(quote: MarketQuote, markets: list[str]) -> bool:
    if not markets:
        return True
    wanted = {m.lower() for m in markets}
    return quote.market.lower() in wanted
