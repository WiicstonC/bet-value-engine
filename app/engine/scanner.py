from collections import Counter
from datetime import datetime, timedelta, timezone

from app.config import EngineConfig
from app.core.confidence import calculate_confidence
from app.core.market_consensus import consensus_probabilities
from app.core.probability import implied_probability
from app.core.value import calculate_edge, calculate_expected_value, classify_value
from app.engine.filters import market_allowed, matches_watchlist
from app.engine.market_catalog import select_deep_markets
from app.models import Candidate, Event, MarketQuote
from app.providers.base import SportsProvider


class Scanner:
    def __init__(self, provider: SportsProvider, config: EngineConfig):
        self.provider = provider
        self.config = config
        self.deep_events_considered = 0
        self.deep_events_with_markets = 0
        self.deep_markets_requested = 0
        self.deep_quotes_received = 0
        self.deep_market_hits: Counter[str] = Counter()

    @staticmethod
    def _consensus_key(quote: MarketQuote) -> tuple[str, float | None, str]:
        line = quote.line
        if line is not None and quote.market.lower() in {"spreads", "alternate_spreads"}:
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
        return any(abs(minutes_to_start - target) <= tolerance for target in self.config.alerts.minutes_before_start)

    def _markets_for_event(self, start_time: datetime, now: datetime, alert_only: bool) -> list[str]:
        markets = list(self.config.watchlist.markets)
        if not alert_only:
            return markets
        if self._in_alert_window(start_time, now):
            return markets
        return ["h2h"]

    def _evaluate_quotes(self, event: Event, quotes: list[MarketQuote], target: str, minimum_confidence: float | None = None, minimum_edge: float | None = None, minimum_expected_value: float | None = None) -> list[Candidate]:
        target_quotes = [q for q in quotes if self._bookmaker_matches(q.bookmaker, target)]
        if not target_quotes:
            return []
        consensus = consensus_probabilities(quotes, excluded_bookmaker=target)
        results: list[Candidate] = []
        confidence_floor = self.config.alerts.minimum_confidence if minimum_confidence is None else minimum_confidence
        edge_floor = self.config.alerts.minimum_edge if minimum_edge is None else minimum_edge
        ev_floor = self.config.alerts.minimum_expected_value if minimum_expected_value is None else minimum_expected_value
        for quote in target_quotes:
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
            if confidence >= confidence_floor and edge >= edge_floor and ev >= ev_floor:
                results.append(Candidate(event=event, quote=quote, model_probability=model_probability, implied_probability=implied, edge=edge, expected_value=ev, confidence=confidence, decision=decision, consensus_bookmakers=bookmaker_count, consensus_dispersion=dispersion))
        return results

    def _target_has_market(self, available: dict[str, set[str]], target: str, markets: list[str]) -> bool:
        for title, bookmaker_markets in available.items():
            if self._bookmaker_matches(title, target) and any(m in bookmaker_markets for m in markets):
                return True
        return False

    def _deep_scan_event(self, event: Event, now: datetime, ignore_time_window: bool = False) -> list[Candidate]:
        if not self.config.deep_scan.enabled:
            return []
        minutes = self._minutes_to_start(event.start_time, now)
        if not ignore_time_window and (minutes < 0 or minutes > self.config.deep_scan.minutes_before_start):
            return []
        self.deep_events_considered += 1
        available = self.provider.available_markets(event)
        if not available:
            return []
        all_available = set().union(*available.values()) if available else set()
        markets = select_deep_markets(event.sport, all_available)[:self.config.deep_scan.max_markets_per_event]
        if not markets:
            return []
        if self.config.deep_scan.only_if_target_bookmaker_has_market:
            if not any(self._target_has_market(available, target, markets) for target in self.config.watchlist.bookmakers):
                return []
        self.deep_events_with_markets += 1
        self.deep_markets_requested += len(markets)
        for market in markets:
            self.deep_market_hits[market] += 1
        try:
            quotes = self.provider.event_quotes(event, markets)
        except Exception as exc:
            print(f"Deep scan error {event.home} vs {event.away}: {exc}")
            return []
        self.deep_quotes_received += len(quotes)
        candidates: list[Candidate] = []
        for target in self.config.watchlist.bookmakers:
            candidates.extend(self._evaluate_quotes(event, quotes, target))
        return candidates

    def analyze_event(self, event: Event) -> list[Candidate]:
        return self._deep_scan_event(event, datetime.now(timezone.utc), ignore_time_window=True)

    def scan_live(self, now: datetime | None = None) -> list[Candidate]:
        now = now or datetime.now(timezone.utc)
        candidates: list[Candidate] = []
        for sport in self.config.watchlist.sports:
            live_events = self.provider.live_events(sport, now, self.config.live.lookback_minutes)
            for event in live_events:
                try:
                    quotes = [q for q in self.provider.quotes(event, self.config.live.markets) if market_allowed(q, self.config.live.markets)]
                except Exception as exc:
                    print(f"Live scan error {event.home} vs {event.away}: {exc}")
                    continue
                for target in self.config.watchlist.bookmakers:
                    candidates.extend(self._evaluate_quotes(event, quotes, target, minimum_confidence=self.config.live.minimum_confidence, minimum_edge=self.config.live.minimum_edge, minimum_expected_value=self.config.live.minimum_expected_value))
        unique: dict[tuple[str, str, str, float | None, str], Candidate] = {}
        for candidate in candidates:
            key = (candidate.event.id, candidate.quote.market, candidate.quote.selection, candidate.quote.line, candidate.quote.bookmaker)
            previous = unique.get(key)
            if previous is None or candidate.confidence > previous.confidence:
                unique[key] = candidate
        result = list(unique.values())
        result.sort(key=lambda c: (c.confidence, c.edge, c.expected_value), reverse=True)
        return result[:self.config.live.max_alerts_per_run]

    def scan(self, start: datetime | None = None, hours: int | None = None, alert_only: bool = False) -> list[Candidate]:
        start = start or datetime.now(timezone.utc)
        end = start + timedelta(hours=hours or self.config.watch_hours)
        candidates: list[Candidate] = []
        all_events: list[Event] = []
        for sport in self.config.watchlist.sports:
            events = self.provider.upcoming_events(sport, start, end)
            all_events.extend(events)
            for event in events:
                if not matches_watchlist(event, self.config.watchlist) or alert_only:
                    continue
                markets = self.config.watchlist.markets
                quotes = [q for q in self.provider.quotes(event, markets) if market_allowed(q, markets)]
                for target in self.config.watchlist.bookmakers:
                    candidates.extend(self._evaluate_quotes(event, quotes, target))
        if self.config.deep_scan.enabled and not self.config.deep_scan.manual_only:
            eligible = [event for event in all_events if matches_watchlist(event, self.config.watchlist) and 0 <= self._minutes_to_start(event.start_time, start) <= self.config.deep_scan.minutes_before_start]
            eligible.sort(key=lambda event: self._minutes_to_start(event.start_time, start))
            for event in eligible[:self.config.deep_scan.max_events_per_run]:
                candidates.extend(self._deep_scan_event(event, start))
        unique: dict[tuple[str, str, str, float | None, str], Candidate] = {}
        for candidate in candidates:
            key = (candidate.event.id, candidate.quote.market, candidate.quote.selection, candidate.quote.line, candidate.quote.bookmaker)
            previous = unique.get(key)
            if previous is None or candidate.confidence > previous.confidence:
                unique[key] = candidate
        result = list(unique.values())
        result.sort(key=lambda c: (c.confidence, c.edge, c.expected_value, c.consensus_bookmakers), reverse=True)
        return result[:self.config.alerts.max_alerts_per_scan]
