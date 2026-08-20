from datetime import datetime

from app.alerts import should_alert
from app.config import EngineConfig
from app.data_models import Event, Market, Opportunity
from app.market_selector import filter_markets
from app.watchlist import filter_events


class Scanner:
    """Coordinates event filtering, market filtering and alert eligibility.

    Data providers and sport-specific models plug into this scanner later.
    The scanner itself stays independent of any bookmaker or API provider.
    """

    def __init__(self, config: EngineConfig):
        self.config = config

    def scan(
        self,
        events: list[Event],
        markets: list[Market],
        opportunities: list[Opportunity],
        now: datetime,
    ) -> list[Opportunity]:
        watched_events = {
            event.event_id for event in filter_events(events, self.config)
        }

        watched_markets = {
            market.market_id
            for market in filter_markets(markets, self.config)
        }

        candidates = [
            opportunity
            for opportunity in opportunities
            if opportunity.event.event_id in watched_events
            and opportunity.market.market_id in watched_markets
        ]

        return [
            opportunity
            for opportunity in candidates
            if should_alert(opportunity, self.config.alerts, now)
        ]
