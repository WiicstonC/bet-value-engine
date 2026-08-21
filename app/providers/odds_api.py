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
        "tennis_atp_aus_open_singles", "tennis_atp_french_open", "tennis_atp_us_open",
        "tennis_atp_wimbledon", "tennis_atp_indian_wells", "tennis_atp_miami_open",
        "tennis_atp_monte_carlo_masters", "tennis_atp_madrid_open", "tennis_atp_italian_open",
        "tennis_atp_canadian_open", "tennis_atp_cincinnati_open", "tennis_atp_shanghai_masters",
        "tennis_atp_paris_masters", "tennis_atp_china_open", "tennis_atp_barcelona_open",
        "tennis_atp_halle_open", "tennis_atp_queens_club_champ", "tennis_atp_washington_open",
        "tennis_atp_dubai", "tennis_atp_qatar_open", "tennis_atp_hamburg_open", "tennis_atp_munich",
        "tennis_wta_aus_open_singles", "tennis_wta_french_open", "tennis_wta_us_open",
        "tennis_wta_wimbledon", "tennis_wta_indian_wells", "tennis_wta_miami_open",
        "tennis_wta_madrid_open", "tennis_wta_italian_open", "tennis_wta_canadian_open",
        "tennis_wta_cincinnati_open", "tennis_wta_china_open", "tennis_wta_dubai",
        "tennis_wta_qatar_open", "tennis_wta_bad_homburg_open", "tennis_wta_charleston_open",
        "tennis_wta_german_open", "tennis_wta_queens_club_champ", "tennis_wta_strasbourg",
        "tennis_wta_stuttgart_open", "tennis_wta_washington_open", "tennis_wta_wuhan_open",
    ],
}

BOOKMAKERS_BY_SPORT = {
    "nba": [
        "betano_uk", "betfair_ex_uk", "betfair_sb_uk", "williamhill",
        "unibet_uk", "betvictor", "betway", "sport888", "betfred_uk", "ladbrokes_uk",
    ],
    "football": [
        "betano_uk", "betfair_ex_uk", "betfair_sb_uk", "williamhill",
        "unibet_uk", "betvictor", "betway", "sport888", "betfred_uk", "ladbrokes_uk",
    ],
    "tennis": [
        "betano_uk", "betfair_ex_uk", "betfair_sb_uk", "williamhill",
        "unibet_uk", "betvictor", "betway", "sport888", "betfred_uk", "ladbrokes_uk",
    ],
}

# One region is intentional: discovery is now a low-cost gate, not a full odds scan.
DISCOVERY_REGIONS = "uk"


class TheOddsAPIProvider(SportsProvider):
    def __init__(self, api_key: str | None = None):
        configured = [
            os.getenv(name, "").strip()
            for name in ("ODDS_API_KEY", "ODDS_API_KEY_2", "ODDS_API_KEY_3")
        ]
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
            request_params = {**params, "apiKey": key}
            try:
                response = httpx.get(f"{self.base_url}{path}", params=request_params, timeout=25)
                self.last_quota_remaining = response.headers.get("x-requests-remaining")
                self.last_quota_used = response.headers.get("x-requests-used")
                self.last_quota_last = response.headers.get("x-requests-last")
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as exc:
                last_error = exc
                status = exc.response.status_code
                if status not in {401, 403, 429} or index >= len(self.api_keys) - 1:
                    raise
                self.failover_count += 1
                continue
            except httpx.HTTPError as exc:
                last_error = exc
                raise

        if last_error:
            raise last_error
        raise RuntimeError("No hay claves de Odds API disponibles.")

    @staticmethod
    def _bookmaker_matches(title: str, wanted: str) -> bool:
        title = title.lower().strip()
        wanted = wanted.lower().strip()
        if wanted == "betano":
            return "betano" in title
        return title == wanted or wanted in title

    def _bookmaker_keys(self, sport: str) -> list[str]:
        return BOOKMAKERS_BY_SPORT.get(sport, BOOKMAKERS_BY_SPORT["football"])

    def upcoming_events(self, sport: str, start: datetime, end: datetime) -> list[Event]:
        events: list[Event] = []
        seen: set[str] = set()

        for sport_key in SPORT_KEYS.get(sport, []):
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
                events.append(Event(
                    id=event_id,
                    sport=sport,
                    competition=sport_key,
                    home=item["home_team"],
                    away=item["away_team"],
                    start_time=start_time,
                ))
        return sorted(events, key=lambda event: event.start_time)

    def live_events(self, sport: str, now: datetime | None = None, lookback_minutes: int = 240) -> list[Event]:
        now = now or datetime.now(timezone.utc)
        start = now.replace(microsecond=0)
        from datetime import timedelta
        start = start - timedelta(minutes=lookback_minutes)
        events = self.upcoming_events(sport, start, now)
        return [event for event in events if event.start_time <= now]

    def event_by_id(self, event_id: str, sport: str) -> Event | None:
        now = datetime.now(timezone.utc)
        from datetime import timedelta
        events = self.upcoming_events(sport, now - timedelta(days=1), now + timedelta(days=3))
        return next((event for event in events if event.id == event_id), None)

    def available_markets(self, event: Event) -> dict[str, set[str]]:
        if event.id in self._markets_cache:
            return self._markets_cache[event.id]

        try:
            data = self._get(
                f"/sports/{event.competition}/events/{event.id}/markets",
                {"regions": DISCOVERY_REGIONS},
            )
        except httpx.HTTPStatusError:
            self._markets_cache[event.id] = {}
            return {}

        result: dict[str, set[str]] = {}
        for bookmaker in data.get("bookmakers", []) if isinstance(data, dict) else []:
            title = bookmaker.get("title", "")
            result[title] = {market.get("key") for market in bookmaker.get("markets", []) if market.get("key")}

        self._markets_cache[event.id] = result
        return result

    def quotes(self, event: Event, markets: list[str]) -> list[MarketQuote]:
        market_keys = tuple(sorted(set(markets or ["h2h"])))
        cache_key = (event.competition, market_keys)
        if cache_key not in self._odds_cache:
            data = self._get(f"/sports/{event.competition}/odds", {
                "bookmakers": ",".join(self._bookmaker_keys(event.sport)),
                "markets": ",".join(market_keys),
                "oddsFormat": "decimal",
            })
            self._odds_cache[cache_key] = data
        return self._parse_quotes(self._odds_cache[cache_key], event.id)

    def event_quotes(self, event: Event, markets: list[str]) -> list[MarketQuote]:
        market_keys = tuple(sorted(set(markets)))
        if not market_keys:
            return []

        cache_key = (event.id, market_keys)
        if cache_key not in self._event_odds_cache:
            data = self._get(
                f"/sports/{event.competition}/events/{event.id}/odds",
                {
                    "bookmakers": ",".join(self._bookmaker_keys(event.sport)),
                    "markets": ",".join(market_keys),
                    "oddsFormat": "decimal",
                },
            )
            self._event_odds_cache[cache_key] = data
        return self._parse_quotes(self._event_odds_cache[cache_key], event.id)

    @staticmethod
    def _parse_quotes(data: list | dict, event_id: str) -> list[MarketQuote]:
        if isinstance(data, dict):
            items = [data]
        else:
            items = data

        quotes: list[MarketQuote] = []
        for item in items:
            for bookmaker in item.get("bookmakers", []):
                for market in bookmaker.get("markets", []):
                    for outcome in market.get("outcomes", []):
                        selection = outcome.get("name", "")
                        description = outcome.get("description")
                        if description:
                            selection = f"{description} | {selection}"
                        quotes.append(MarketQuote(
                            event_id=event_id,
                            market=market["key"],
                            selection=selection,
                            line=outcome.get("point"),
                            odds=float(outcome["price"]),
                            bookmaker=bookmaker["title"],
                            updated_at=datetime.fromisoformat(
                                market.get("last_update", item.get("commence_time")).replace("Z", "+00:00")
                            ),
                        ))
        return quotes
