import os
from datetime import datetime

import httpx

from app.models import Event, MarketQuote
from app.providers.base import SportsProvider


SPORT_KEYS = {
    "nba": ["basketball_nba"],
    "football": [
        "soccer_epl",
        "soccer_spain_la_liga",
        "soccer_italy_serie_a",
        "soccer_germany_bundesliga",
        "soccer_france_ligue_one",
        "soccer_colombia_primera_a",
    ],
    "tennis": [
        # Grand Slams
        "tennis_atp_aus_open_singles",
        "tennis_atp_french_open",
        "tennis_atp_us_open",
        "tennis_atp_wimbledon",
        "tennis_wta_aus_open_singles",
        "tennis_wta_french_open",
        "tennis_wta_us_open",
        "tennis_wta_wimbledon",
        # ATP Masters / major ATP events
        "tennis_atp_indian_wells",
        "tennis_atp_miami_open",
        "tennis_atp_monte_carlo_masters",
        "tennis_atp_madrid_open",
        "tennis_atp_italian_open",
        "tennis_atp_canadian_open",
        "tennis_atp_cincinnati_open",
        "tennis_atp_shanghai_masters",
        "tennis_atp_paris_masters",
        "tennis_atp_china_open",
        "tennis_atp_barcelona_open",
        "tennis_atp_halle_open",
        "tennis_atp_queens_club_champ",
        "tennis_atp_washington_open",
        "tennis_atp_dubai",
        "tennis_atp_qatar_open",
        "tennis_atp_hamburg_open",
        "tennis_atp_munich",
        # WTA 1000 / major WTA events
        "tennis_wta_indian_wells",
        "tennis_wta_miami_open",
        "tennis_wta_madrid_open",
        "tennis_wta_italian_open",
        "tennis_wta_canadian_open",
        "tennis_wta_cincinnati_open",
        "tennis_wta_china_open",
        "tennis_wta_dubai",
        "tennis_wta_qatar_open",
        "tennis_wta_bad_homburg_open",
        "tennis_wta_charleston_open",
        "tennis_wta_german_open",
        "tennis_wta_queens_club_champ",
        "tennis_wta_strasbourg",
        "tennis_wta_stuttgart_open",
        "tennis_wta_washington_open",
        "tennis_wta_wuhan_open",
    ],
}


class TheOddsAPIProvider(SportsProvider):
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("ODDS_API_KEY")
        if not self.api_key:
            raise RuntimeError("Falta ODDS_API_KEY en las variables de entorno.")
        self.base_url = "https://api.the-odds-api.com/v4"

    def _get(self, path: str, params: dict) -> list[dict]:
        params = {**params, "apiKey": self.api_key}
        response = httpx.get(f"{self.base_url}{path}", params=params, timeout=20)
        response.raise_for_status()
        return response.json()

    def upcoming_events(self, sport: str, start: datetime, end: datetime) -> list[Event]:
        events: list[Event] = []
        seen: set[str] = set()

        for sport_key in SPORT_KEYS.get(sport, []):
            try:
                data = self._get(f"/sports/{sport_key}/events", {})
            except httpx.HTTPStatusError:
                # Un torneo fuera de temporada puede dejar de estar disponible.
                # No debemos tumbar todo el escaneo por una competición inactiva.
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
        data = self._get(f"/sports/{event.competition}/odds", {
            "regions": "eu",
            "markets": ",".join(markets or ["h2h", "spreads", "totals"]),
            "oddsFormat": "decimal",
        })
        quotes: list[MarketQuote] = []
        for item in data:
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
