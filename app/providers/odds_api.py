import os
from datetime import datetime

import httpx

from app.models import Event, MarketQuote
from app.providers.base import SportsProvider


SPORT_KEYS = {
    "tennis": ["tennis_atp", "tennis_wta"],
    "nba": ["basketball_nba"],
    "football": [
        "soccer_epl",
        "soccer_spain_la_liga",
        "soccer_italy_serie_a",
        "soccer_germany_bundesliga",
        "soccer_uefa_champs_league",
        "soccer_colombia_primera_a",
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
        for sport_key in SPORT_KEYS.get(sport, []):
            data = self._get(f"/sports/{sport_key}/events", {})
            for item in data:
                start_time = datetime.fromisoformat(item["commence_time"].replace("Z", "+00:00"))
                if start <= start_time <= end:
                    events.append(Event(
                        id=item["id"],
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
                            updated_at=datetime.fromisoformat(item["commence_time"].replace("Z", "+00:00")),
                        ))
        return quotes
