from datetime import datetime, timedelta, timezone

from app.config import EngineConfig
from app.core.confidence import calculate_confidence
from app.core.market_consensus import consensus_probabilities
from app.core.probability import implied_probability
from app.core.value import calculate_edge, calculate_expected_value, classify_value
from app.engine.filters import market_allowed, matches_watchlist
from app.models import Candidate
from app.providers.base import SportsProvider


class Scanner:
    def __init__(self, provider: SportsProvider, config: EngineConfig):
        self.provider = provider
        self.config = config

    @staticmethod
    def _consensus_key(quote) -> tuple[str, float | None, str]:
        line = quote.line
        if line is not None and quote.market.lower() == "spreads":
            line = abs(line)
        return (quote.market.lower(), line, quote.selection.lower())

    @staticmethod
    def _bookmaker_matches(title: str, wanted: str) -> bool:
        title = title.lower().strip()
        wanted = wanted.lower().strip()
        if wanted == "betano":
            return "betano" in title
        return title == wanted or wanted in title

    def _minutes_to_start(self, start_time: datetime, now: datetime) -> float:
        return (start_time - now).total_seconds() / 60

    def _in_alert_window(self, start_time: datetime, now: datetime) -> bool:
        minutes_to_start = self._minutes_to_start(start_time, now)
        tolerance = max(self.config.scan_interval_minutes / 2, 2)
        return any(abs(minutes_to_start - target) <= tolerance
                   for target in self.config.alerts.minutes_before_start)

    def _markets_for_event(self, event_start: datetime, now: datetime, alert_only: bool) -> list[str]:
        configured = self.config.watchlist.markets
        if not alert_only:
            return configured

        minutes = self._minutes_to_start(event_start, now)
        # Preserve quota on the frequent 10-minute scheduler. We use the
        # cheap match-winner market for early checks and open all configured
        # featured markets only near kickoff, when the signal is actionable.
        if minutes <= 20:
            return configured
        return ["h2h"] if "h2h" in configured else configured[:1]

    def scan(
        self,
        start: datetime | None = None,
        hours: int | None = None,
        alert_only: bool = False,
    ) -> list[Candidate]:
        start = start or datetime.now(timezone.utc)
        end = start + timedelta(hours=hours or self.config.watch_hours)
        candidates: list[Candidate] = []

        for sport in self.config.watchlist.sports:
            events = self.provider.upcoming_events(sport, start, end)
            for event in events:
                if alert_only and not self._in_alert_window(event.start_time, start):
                    continue
                if not matches_watchlist(event, self.config.watchlist):
                    continue

                markets = self._markets_for_event(event.start_time, start, alert_only)
                quotes = [
                    q for q in self.provider.quotes(event, markets)
                    if market_allowed(q, markets)
                ]
                if not quotes:
                    continue

                target_quotes = [
                    q for q in quotes
                    if any(self._bookmaker_matches(q.bookmaker, target)
                           for target in self.config.watchlist.bookmakers)
                ]
                if not target_quotes:
                    continue

                for target in self.config.watchlist.bookmakers:
                    target_specific = [
                        q for q in target_quotes if self._bookmaker_matches(q.bookmaker, target)
                    ]
                    if not target_specific:
                        continue

                    consensus = consensus_probabilities(quotes, excluded_bookmaker=target)

                    for quote in target_specific:
                        consensus_data = consensus.get(self._consensus_key(quote))
                        if not consensus_data:
                            continue

                        model_probability, bookmaker_count, dispersion = consensus_data
                        if bookmaker_count < self.config.alerts.minimum_consensus_bookmakers:
                            continue

                        implied = implied_probability(quote.odds)
                        edge = calculate_edge(model_probability, implied)
                        ev = calculate_expected_value(model_probability, quote.odds)

                        book_quality = min(bookmaker_count / 5.0, 1.0)
                        agreement = max(0.0, 1.0 - dispersion * 5.0)
                        edge_quality = min(max(edge * 4.0, 0.0), 1.0)
                        confidence = calculate_confidence({
                            "statistics": 0.70,
                            "edge": edge_quality,
                            "form": 0.60,
                            "context": 0.60,
                            "market": min(0.65 + book_quality * 0.35, 1.0),
                            "data_quality": book_quality,
                            "uncertainty": agreement,
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
                                model_probability=model_probability,
                                implied_probability=implied,
                                edge=edge,
                                expected_value=ev,
                                confidence=confidence,
                                decision=decision,
                                consensus_bookmakers=bookmaker_count,
                                consensus_dispersion=dispersion,
                            ))

        candidates.sort(
            key=lambda c: (c.confidence, c.edge, c.expected_value, c.consensus_bookmakers),
            reverse=True,
        )
        return candidates
