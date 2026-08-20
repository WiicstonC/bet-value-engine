from datetime import datetime, timedelta, timezone

from app.config import EngineConfig
from app.engine.filters import market_allowed, matches_watchlist
from app.models import Candidate
from app.providers.base import SportsProvider
from app.core.confidence import calculate_confidence
from app.core.probability import implied_probability
from app.core.value import calculate_edge, calculate_expected_value, classify_value


class Scanner:
    def __init__(self, provider: SportsProvider, config: EngineConfig):
        self.provider = provider
        self.config = config

    def scan(self, start: datetime | None = None, hours: int = 48) -> list[Candidate]:
        start = start or datetime.now(timezone.utc)
        end = start + timedelta(hours=hours)
        candidates: list[Candidate] = []

        for sport in self.config.watchlist.sports:
            for event in self.provider.upcoming_events(sport, start, end):
                if not matches_watchlist(event, self.config.watchlist):
                    continue

                quotes = self.provider.quotes(event, self.config.watchlist.markets)
                for quote in quotes:
                    if not market_allowed(quote, self.config.watchlist.markets):
                        continue

                    # Hasta conectar los modelos estadísticos independientes,
                    # usamos la probabilidad implícita como baseline neutral.
                    # Esto evita inventar edge donde todavía no existe modelo.
                    model_probability = implied_probability(quote.odds)
                    edge = calculate_edge(model_probability, implied_probability(quote.odds))
                    ev = calculate_expected_value(model_probability, quote.odds)
                    confidence = calculate_confidence({"data_quality": 0.5})
                    decision = classify_value(edge, ev)

                    if (
                        confidence >= self.config.alerts.minimum_confidence
                        and edge >= self.config.alerts.minimum_edge
                        and ev >= self.config.alerts.minimum_expected_value
                    ):
                        candidates.append(Candidate(
                            event=event,
                            quote=quote,
                            model_probability=model_probability,
                            implied_probability=implied_probability(quote.odds),
                            edge=edge,
                            expected_value=ev,
                            confidence=confidence,
                            decision=decision,
                        ))

        return candidates
