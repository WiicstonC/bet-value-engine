import os
from datetime import datetime, timezone

import httpx

from app.models import Event, MarketQuote
from app.providers.base import SportsProvider


SPORT_KEYS = {
    "nba": ["basketball_nba"],
    "football": [
        "soccer_epl", "soccer_spain_la_liga", "soccer_italy_serie_a",
        "soccer_germany_bundesliga", "soccer_france_ligue_one", "soccer_colombia_primera_a",
    ],
    "tennis": [
        "tennis_atp_aus_open_singles", "tennis_atp_french_open", "tennis_atp_us_open", "tennis_atp_wimbledon",
        "tennis_atp_indian_wells", "tennis_atp_miami_open", "tennis_atp_monte_carlo_masters", "tennis_atp_madrid_open",
        "tennis_atp_italian_open", "tennis_atp_canadian_open", "tennis_atp_cincinnati_open", "tennis_atp_shanghai_masters",
        "tennis_atp_paris_masters", "tennis_atp_china_open", "tennis_atp_barcelona_open", "tennis_atp_halle_open",
        "tennis_atp_queens_club_champ", "tennis_atp_washington_open", "tennis_atp_dubai", "tennis_atp_qatar_open",
        "tennis_atp_hamburg_open", "tennis_atp_munich", "tennis_wta_aus_open_singles", "tennis_wta_french_open",
        "tennis_wta_us_open", "tennis_wta_wimbledon", "tennis_wta_indian_wells", "tennis_wta_miami_open",
        "tennis_wta_madrid_open", "tennis_wta_italian_open", "tennis_wta_canadian_open", "tennis_wta_cincinnati_open",
        "tennis_wta_china_open", "tennis_wta_dubai", "tennis_wta_qatar_open", "tennis_wta_bad_homburg_open",
        "tennis_wta_charleston_open", "tennis_wta_german_open", "tennis_wta_queens_club_champ", "tennis_wta_strasbourg",
        "tennis_wta_stuttgart_open", "tennis_wta_washington_open", "tennis_wta_wuhan_open",
    ],
}

BOOKMAKERS_BY_SPORT = {
    "nba": ["betano_uk", "betfair_ex_uk", "betfair_sb_uk", "williamhill", "unibet_uk", "betvictor", "betway", "sport888", "betfred_uk", "ladbrokes_uk"],
    "football": ["betano_uk", "betfair_ex_uk", "betfair_sb_uk", "williamhill", "unibet_uk", "betvictor", "betway", "sport888", "betfred_uk", "ladbrokes_uk"],
    "tennis": ["betano_uk", "betfair_ex_uk", "betfair_sb_uk", "williamhill", "unibet_uk", "betvictor", "betway", "sport888", "betfred_uk", "ladbrokes_uk"],
}

DISCOVERY_REGIONS = "uk"


class TheOddsAPIProvider(SportsProvider):
    def __init__(self, api_key: str | None = None):
        configured = [os.getenv(name, "").strip() for name in ("ODDS_API_KEY", "ODDS_API_KEY_2", "ODDS_API_KEY_3")]
        configured = [key for key in configured if key]
        if api_key:
            configured = [api_key] + [key for key in configured if key != api_key]
        if not configured:
            raise RuntimeError("Falta al menos una ODDS_API_KEY en las variables de entorno.")
        self.api_keys = configured
        self.key_index = 0
        self.base_url = "https://api.the-odds-api.com/v4"
        self._odds_cache: dict[tuple[str, tuple[str, ...]], list[dict]] = {}
        self._event_odds_cache: dict[tuple[str, tuple[str, ...]], list[dict]] = {}
        self._markets_cache: dict[str, dict[str, set[str]]] = {}
        self._scores_cache: dict[str, list[dict]] = {}
        self._active_sports_cache: list[dict] | None = None
        self.last_quota_remaining: str | None = None
        self.last_quota_used: str | None = None
        self.last_quota_last: str | None = None
        self.last_key_index: int = 0
        self.failover_count = 0

    @property
    def active_key_number(self) -> int:
        return self.key_index + 1

    def _get(self, path: str, params: dict) -> list | dict:
        last_error: Exception | None = None
        for index in range(self.key_index, len(self.api_keys)):
            self.key_index = index
            self.last_key_index = index
            key = self.api_keys[index]
            try:
                response = httpx.get(f"{self.base_url}{path}", params={**params, "apiKey": key}, timeout=25)
                self.last_quota_remaining = response.headers.get("x-requests-remaining")
                self.last_quota_used = response.headers.get("x-requests-used")
                self.last_quota_last = response.headers.get("x-requests-last")
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as exc:
                last_error = exc
                if exc.response.status_code not in {401, 403, 429} or index >= len(self.api_keys) - 1:
                    raise
                self.failover_count += 1
            except httpx.HTTPError as exc:
                last_error = exc
                raise
        if last_error:
            raise last_error
        raise RuntimeError("No hay claves de Odds API disponibles.")

    def active_sport_keys(self, sport: str) -> list[str]:
        """Use the API's active-sports catalog to avoid querying every historical tennis tournament."""
        try:
            if self._active_sports_cache is None:
                data = self._get("/sports", {})
                self._active_sports_cache = data if isinstance(data, list) else []
            active = {str(item.get("key")) for item in self._active_sports_cache}
            configured = SPORT_KEYS.get(sport, [])
            if sport == "tennis":
                dynamic = sorted(key for key in active if key.startswith(("tennis_atp_", "tennis_wta_")))
                return dynamic or configured
            return [key for key in configured if key in active] or configured
        except Exception as exc:
            print(f"No se pudo consultar catálogo activo: {exc}")
            return SPORT_KEYS.get(sport, [])

    @staticmethod
    def _bookmaker_matches(title: str, wanted: str) -> bool:
        title, wanted = title.lower().strip(), wanted.lower().strip()
        return "betano" in title if wanted == "betano" else title == wanted or wanted in title

    def _bookmaker_keys(self, sport: str) -> list[str]:
        return BOOKMAKERS_BY_SPORT.get(sport, BOOKMAKERS_BY_SPORT["football"])

    def upcoming_events(self, sport: str, start: datetime, end: datetime) -> list[Event]:
        events, seen = [], set()
        for sport_key in self.active_sport_keys(sport):
            try:
                data = self._get(f"/sports/{sport_key}/events", {})
            except httpx.HTTPStatusError:
                continue
            for item in data:
                start_time = datetime.fromisoformat(item["commence_time"].replace("Z", "+00:00"))
                event_id = item["id"]
                if event_id in seen or not (start <= start_time <= end):
                    continue
                seen.add(event_id)
                events.append(Event(id=event_id, sport=sport, competition=sport_key, home=item["home_team"], away=item["away_team"], start_time=start_time))
        return sorted(events, key=lambda event: event.start_time)

    def live_events(self, sport: str, now: datetime | None = None, lookback_minutes: int = 240) -> list[Event]:
        now = now or datetime.now(timezone.utc)
        events = []
        for sport_key in self.active_sport_keys(sport):
            try:
                data = self._get(f"/sports/{sport_key}/scores", {"daysFrom": 1})
            except httpx.HTTPStatusError:
                continue
            for item in data:
                commence = datetime.fromisoformat(item["commence_time"].replace("Z", "+00:00"))
                if not item.get("completed") and commence <= now:
                    events.append(Event(id=item["id"], sport=sport, competition=sport_key, home=item["home_team"], away=item["away_team"], start_time=commence))
        return sorted({event.id: event for event in events}.values(), key=lambda event: event.start_time)

    def event_by_id(self, event_id: str, sport: str) -> Event | None:
        from datetime import timedelta
        now = datetime.now(timezone.utc)
        events = self.upcoming_events(sport, now - timedelta(days=1), now + timedelta(days=3))
        return next((event for event in events if event.id == event_id), None)

    def available_markets(self, event: Event) -> dict[str, set[str]]:
        if event.id in self._markets_cache:
            return self._markets_cache[event.id]
        try:
            data = self._get(f"/sports/{event.competition}/events/{event.id}/markets", {"regions": DISCOVERY_REGIONS})
        except httpx.HTTPStatusError:
            self._markets_cache[event.id] = {}
            return {}
        if not isinstance(data, dict):
            self._markets_cache[event.id] = {}
            return {}
        result = {b.get("title", ""): {m.get("key") for m in b.get("markets", []) if m.get("key")} for b in data.get("bookmakers", [])}
        self._markets_cache[event.id] = result
        return result

    def quotes(self, event: Event, markets: list[str]) -> list[MarketQuote]:
        market_keys = tuple(sorted(set(markets or ["h2h"])))
        cache_key = (event.competition, market_keys)
        if cache_key not in self._odds_cache:
            self._odds_cache[cache_key] = self._get(f"/sports/{event.competition}/odds", {"bookmakers": ",".join(self._bookmaker_keys(event.sport)), "markets": ",".join(market_keys), "oddsFormat": "decimal"})
        return self._parse_quotes(self._odds_cache[cache_key], event.id)

    def event_quotes(self, event: Event, markets: list[str]) -> list[MarketQuote]:
        market_keys = tuple(sorted(set(markets)))
        if not market_keys:
            return []
        cache_key = (event.id, market_keys)
        if cache_key not in self._event_odds_cache:
            self._event_odds_cache[cache_key] = self._get(f"/sports/{event.competition}/events/{event.id}/odds", {"bookmakers": ",".join(self._bookmaker_keys(event.sport)), "markets": ",".join(market_keys), "oddsFormat": "decimal"})
        return self._parse_quotes(self._event_odds_cache[cache_key], event.id)

    def completed_event(self, event: Event) -> dict | None:
        if event.competition not in self._scores_cache:
            try:
                data = self._get(f"/sports/{event.competition}/scores", {"daysFrom": 3})
            except httpx.HTTPStatusError:
                self._scores_cache[event.competition] = []
                return None
            self._scores_cache[event.competition] = data if isinstance(data, list) else []
        return next((item for item in self._scores_cache[event.competition] if item.get("id") == event.id and item.get("completed")), None)

    @staticmethod
    def score_map(score_item: dict) -> dict[str, int]:
        values = {}
        for item in score_item.get("scores", []) or []:
            try:
                values[str(item.get("name"))] = int(float(item.get("score")))
            except (TypeError, ValueError):
                continue
        return values

    @staticmethod
    def settle_score_market(row: dict, score_item: dict) -> str | None:
        scores = TheOddsAPIProvider.score_map(score_item)
        home, away = score_item.get("home_team"), score_item.get("away_team")
        if home not in scores or away not in scores:
            return None
        home_score, away_score = scores[home], scores[away]
        market, selection, line = str(row.get("market", "")).lower(), str(row.get("selection", "")), row.get("line")
        if market == "h2h":
            if selection == home:
                return "won" if home_score > away_score else "lost" if home_score < away_score else "void"
            if selection == away:
                return "won" if away_score > home_score else "lost" if away_score < home_score else "void"
            return None
        if market in {"spreads", "alternate_spreads"} and line is not None:
            margin = home_score - away_score if selection == home else away_score - home_score if selection == away else None
            if margin is None:
                return None
            result = margin + float(line)
            return "won" if result > 0 else "lost" if result < 0 else "void"
        if market in {"totals", "alternate_totals"} and line is not None:
            total = home_score + away_score
            result = total - float(line) if selection.lower() == "over" else float(line) - total if selection.lower() == "under" else None
            if result is None:
                return None
            return "won" if result > 0 else "lost" if result < 0 else "void"
        return None

    @staticmethod
    def _parse_quotes(data: list | dict, event_id: str) -> list[MarketQuote]:
        items = [data] if isinstance(data, dict) else data
        quotes = []
        for item in items:
            for bookmaker in item.get("bookmakers", []):
                for market in bookmaker.get("markets", []):
                    for outcome in market.get("outcomes", []):
                        selection = outcome.get("name", "")
                        if outcome.get("description"):
                            selection = f"{outcome['description']} | {selection}"
                        quotes.append(MarketQuote(event_id=event_id, market=market["key"], selection=selection, line=outcome.get("point"), odds=float(outcome["price"]), bookmaker=bookmaker["title"], updated_at=datetime.fromisoformat(market.get("last_update", item.get("commence_time")).replace("Z", "+00:00"))))
        return quotes
