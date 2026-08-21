from datetime import datetime, timezone
import hashlib

import httpx

from app.models import LiveIncident


LEAGUES = {
    "football": {
        "soccer_epl": "soccer/eng.1",
        "soccer_spain_la_liga": "soccer/esp.1",
        "soccer_italy_serie_a": "soccer/ita.1",
        "soccer_germany_bundesliga": "soccer/ger.1",
        "soccer_france_ligue_one": "soccer/fra.1",
        "soccer_colombia_primera_a": "soccer/col.1",
    },
    "nba": {"basketball_nba": "basketball/nba"},
}

HIGH_IMPACT = {
    "red_card": "critical",
    "penalty": "high",
    "goal": "high",
    "injury": "high",
    "ejection": "critical",
    "technical_foul": "high",
}

MEDIUM_IMPACT = {"yellow_card": "medium", "substitution": "medium"}


class ESPNLiveProvider:
    base_url = "https://site.api.espn.com/apis/site/v2/sports"

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    def _get(self, url: str, params: dict | None = None) -> dict:
        response = httpx.get(url, params=params or {}, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _event_teams(event: dict) -> tuple[str, str]:
        competitors = event.get("competitions", [{}])[0].get("competitors", [])
        home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0] if competitors else {})
        away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1] if len(competitors) > 1 else {})
        return (
            home.get("team", {}).get("displayName", home.get("displayName", "Home")),
            away.get("team", {}).get("displayName", away.get("displayName", "Away")),
        )

    @staticmethod
    def _score(event: dict) -> tuple[int | None, int | None]:
        competitors = event.get("competitions", [{}])[0].get("competitors", [])
        values = {}
        for c in competitors:
            try:
                values[c.get("homeAway")] = int(float(c.get("score", 0)))
            except (TypeError, ValueError):
                values[c.get("homeAway")] = None
        return values.get("home"), values.get("away")

    @staticmethod
    def _classify(text: str, sport: str) -> tuple[str | None, str]:
        lower = text.lower()
        if sport == "football":
            if "red card" in lower or "sent off" in lower or "dismissed" in lower:
                return "red_card", HIGH_IMPACT["red_card"]
            if "penalty" in lower:
                return "penalty", HIGH_IMPACT["penalty"]
            if "goal" in lower or "scores" in lower or "scored" in lower:
                return "goal", HIGH_IMPACT["goal"]
            if "injury" in lower or "injured" in lower:
                return "injury", HIGH_IMPACT["injury"]
            if "yellow card" in lower:
                return "yellow_card", MEDIUM_IMPACT["yellow_card"]
            if "substitution" in lower or "substituted" in lower:
                return "substitution", MEDIUM_IMPACT["substitution"]
        if sport == "nba":
            if "ejected" in lower or "ejection" in lower:
                return "ejection", HIGH_IMPACT["ejection"]
            if "technical foul" in lower:
                return "technical_foul", HIGH_IMPACT["technical_foul"]
            if "injury" in lower or "injured" in lower:
                return "injury", HIGH_IMPACT["injury"]
        return None, "low"

    def live_events(self, sport: str) -> list[dict]:
        results: list[dict] = []
        for competition, path in LEAGUES.get(sport, {}).items():
            try:
                data = self._get(f"{self.base_url}/{path}/scoreboard")
            except httpx.HTTPError as exc:
                print(f"ESPN scoreboard error {competition}: {exc}")
                continue
            for event in data.get("events", []):
                status = event.get("status", {}).get("type", {})
                if status.get("state") != "in":
                    continue
                results.append({"competition": competition, "path": path, "event": event})
        return results

    def incidents(self, sport: str) -> list[LiveIncident]:
        incidents: list[LiveIncident] = []
        for item in self.live_events(sport):
            event = item["event"]
            competition = item["competition"]
            path = item["path"]
            event_id = str(event.get("id"))
            home, away = self._event_teams(event)
            score_home, score_away = self._score(event)
            status = event.get("status", {})
            clock = status.get("displayClock")
            try:
                summary = self._get(f"{self.base_url}/{path}/summary", {"event": event_id})
            except httpx.HTTPError as exc:
                print(f"ESPN summary error {event_id}: {exc}")
                continue

            candidates = []
            for key in ("plays", "keyEvents"):
                value = summary.get(key)
                if isinstance(value, list):
                    candidates.extend(value)
            if not candidates:
                candidates = self._find_play_dicts(summary)

            for play in candidates:
                text = str(play.get("text") or play.get("description") or play.get("shortText") or "").strip()
                kind, impact = self._classify(text, sport)
                if not kind or not text:
                    continue
                raw_id = str(play.get("id") or play.get("sequenceNumber") or play.get("createdAt") or text)
                incident_id = hashlib.sha1(f"{event_id}|{raw_id}".encode()).hexdigest()
                timestamp = play.get("wallclock") or play.get("date") or event.get("date")
                try:
                    occurred_at = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
                    if occurred_at.tzinfo is None:
                        occurred_at = occurred_at.replace(tzinfo=timezone.utc)
                except (TypeError, ValueError):
                    occurred_at = datetime.now(timezone.utc)
                team = None
                if isinstance(play.get("team"), dict):
                    team = play["team"].get("displayName")
                athlete = play.get("athletes") or []
                player = None
                if athlete and isinstance(athlete[0], dict):
                    player = athlete[0].get("displayName") or athlete[0].get("fullName")
                incidents.append(LiveIncident(
                    id=incident_id,
                    event_id=event_id,
                    sport=sport,
                    competition=competition,
                    home=home,
                    away=away,
                    occurred_at=occurred_at,
                    kind=kind,
                    description=text,
                    team=team,
                    player=player,
                    score_home=score_home,
                    score_away=score_away,
                    clock=clock,
                    impact=impact,
                ))
        unique = {item.id: item for item in incidents}
        return sorted(unique.values(), key=lambda item: item.occurred_at)

    def _find_play_dicts(self, value):
        found = []
        if isinstance(value, dict):
            if any(key in value for key in ("text", "description", "shortText")) and any(key in value for key in ("id", "sequenceNumber", "date")):
                found.append(value)
            for child in value.values():
                found.extend(self._find_play_dicts(child))
        elif isinstance(value, list):
            for child in value:
                found.extend(self._find_play_dicts(child))
        return found
