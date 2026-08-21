import os
from datetime import datetime

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

# The Odds API currently documents Betano under betano_uk.
# Ten bookmaker keys are used so the request remains within one region-equivalent.
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


class TheOddsAPIProvider(SportsProvider):
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("ODDS_API_KEY")
        if not self.api_key:
            raise RuntimeError("Falta ODDS_API_KEY en las variables de entorno.")
        self.base_url = "https://api.the-odds-api.com/v4"
        self._odds_cache: dict[tuple[str, tuple[str, ...]], list[dict]] = {}
        self.last_quota_remaining: str | None = None
        self.last_quota_used: str | None = None

    def _get(self, path: str, params: dict) -> list[dict]:
        params = {**params, "apiKey": self.api_key}
        response = httpx.get(f"{self.base_url}{path}", params=params, timeout=25)
        self.last_quota_remaining = response.headers.get("x-requests-remaining")
        self.last_quota_used = response.headers.get("x-requests-used")
        response.raise_for_status()
        return response.json()

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

        return events

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

        quotes: list[MarketQuote] = []
        for item in self._odds_cache[cache_key]:
            if item.get("id") != event.id:
                continue
            for bookmaker in item.get("bookmakers", []):
                for market in bookmaker.get("markets", []):
                    for outcome in market.get("outcomes", []):
                        quotes.append(MarketQuote(
                            event_id=event.id,
                            market=market["key"],
                            selection=outcome["name"],
                            line=outcome.get("point"),
                            odds=float(outcome["price"]),
                            bookmaker=bookmaker["title"],
                            updated_at=datetime.fromisoformat(
                                market.get("last_update", item["commence_time"]).replace("Z", "+00:00")
                            ),
                        ))
        return quotes
