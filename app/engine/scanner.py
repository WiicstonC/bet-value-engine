from collections import defaultdict
from datetime import datetime, timedelta, timezone
from statistics import median

from app.config import EngineConfig
from app.engine.filters import market_allowed, matches_watchlist
from app.models import Candidate, MarketQuote
from app.providers.base import SportsProvider
from app.core.confidence import calculate_confidence
from app.core.probability import implied_probability
from app.core.value import calculate_edge, calculate_expected_value, classify_value


def _key(quote: MarketQuote) -> tuple[str, str, str, float | None]:
    return (quote.event_id, quote.market, quote.selection, quote.line)


class Scanner:
    def __init__(self, provider: SportsProvider, config: EngineConfig):
        self.provider = provider
        self.config = config

    def scan(self, start: datetime | None = None, hours: int | None = None) -> list[Candidate]:
        start = start or datetime.now(timezone.utc)
        end = start + timedelta(hours=hours or self.config.watch_hours)
        candidates: list[Candidate] = []

        for sport in self.config.watchlist.sports:
            for event in self.provider.upcoming_events(sport, start, end):
                if not matches_watchlist(event, self.config.watchlist):
                    continue

                quotes = [
                    q for q in self.provider.quotes(event, self.config.watchlist.markets)
                    if market_allowed(q, self.config.watchlist.markets)
                ]
                if not quotes:
                    continue

                groups: dict[tuple[str, str, float | None], list[MarketQuote]] = defaultdict(list)
                for quote in quotes:
                    groups[(quote.market, quote.selection, quote.line)].append(quote)

                for _, market_quotes in groups.items():
                    target_quotes = [
                        q for q in market_quotes
                        if any(q.bookmaker.lower() == b.lower() for b in self.config.watchlist.bookmakers)
                    ]
                    if not target_quotes:
                        continue

                    other_books = [
                        implied_probability(q.odds)
                        for q in market_quotes
                        if all(q.bookmaker.lower() != b.lower() for b in self.config.watchlist.bookmakers)
                    ]
                    if not other_books:
                        continue

                    # Primera capa real del motor: compara Betano contra el consenso
                    # de las demás casas. Esto es line-shopping, no un modelo estadístico.
                    consensus_probability = median(other_books)

                    for quote in target_quotes:
                        market_probability = implied_probability(quote.odds)
                        edge = calculate_edge(consensus_probability, market_probability)
                        ev = calculate_expected_value(consensus_probability, quote.odds)

                        # Sin modelo deportivo independiente, la confianza queda limitada.
                        confidence = calculate_confidence({
                            "statistics": 0.50,
                            "edge": min(max(edge * 5, 0.0), 1.0),
                            "form": 0.50,
                            "context": 0.50,
                            "market": 0.90,
                            "data_quality": 0.80,
                            "uncertainty": 0.30,
                        })

                        decision = classify_value(edge, ev)

                        if (
                            confidence >= self.config.alerts.minimum_confidence
                            and edge >= self.config.alerts.minimum_edge
                            and ev >= self.config.alerts.minimum_expected_value
                        ):
                            candidates.append(Candidate(
                                event=event,
                                quote=quote,
                                model_probability=consensus_probability,
                                implied_probability=market_probability,
                                edge=edge,
                                expected_value=ev,
                                confidence=confidence,
                                decision=decision,
                            ))

        return candidates
