from app.config import EngineConfig
from app.data_models import Market


def market_is_watched(market: Market, config: EngineConfig) -> bool:
    selected = {value.strip().lower() for value in config.watchlist.markets if value.strip()}

    if not selected:
        return True

    normalized_name = market.name.strip().lower()
    normalized_id = market.market_id.strip().lower()

    return normalized_name in selected or normalized_id in selected


def filter_markets(markets: list[Market], config: EngineConfig) -> list[Market]:
    return [market for market in markets if market_is_watched(market, config)]
