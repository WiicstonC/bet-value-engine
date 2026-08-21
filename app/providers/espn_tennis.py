from datetime import datetime, timezone
import hashlib

import httpx

from app.models import LiveIncident


class ESPNTennisLiveProvider:
    base_url = "https://site.api.espn.com/apis/site/v2/sports/tennis"

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    def _get(self, tour: str) -> dict:
        response = httpx.get(f"{self.base_url}/{tour}/scoreboard", timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def incidents(self) -> list[LiveIncident]:
        results = []
        for tour in ("atp", "wta"):
            try:
                data = self._get(tour)
            except httpx.HTTPError as exc:
                print(f"ESPN tennis error {tour}: {exc}")
                continue
            for event in data.get("events", []):
                for grouping in event.get("groupings", []):
                    for competition in grouping.get("competitions", []):
                        status = competition.get("status", {})
                        state = status.get("type", {}).get("state")
                        if state != "in":
                            continue
                        competitors = competition.get("competitors", [])
                        if len(competitors) < 2:
                            continue
                        home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
                        away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])
                        home_name = home.get("athlete", {}).get("displayName", "Player A")
                        away_name = away.get("athlete", {}).get("displayName", "Player B")
                        period = int(status.get("period", 0) or 0)
                        if period <= 0:
                            continue
                        scores = []
                        for competitor in competitors:
                            scores.append(",".join(str(int(line.get("value", 0))) for line in competitor.get("linescores", [])))
                        raw = f"{competition.get('id')}|{period}|{'|'.join(scores)}"
                        incident_id = hashlib.sha1(raw.encode()).hexdigest()
                        occurred_at = competition.get("date") or event.get("date")
                        try:
                            when = datetime.fromisoformat(str(occurred_at).replace("Z", "+00:00"))
                            if when.tzinfo is None:
                                when = when.replace(tzinfo=timezone.utc)
                        except (TypeError, ValueError):
                            when = datetime.now(timezone.utc)
                        results.append(LiveIncident(
                            id=incident_id,
                            event_id=str(competition.get("id")),
                            sport="tennis",
                            competition=f"tennis_{tour}",
                            home=home_name,
                            away=away_name,
                            occurred_at=when,
                            kind="set_change",
                            description=f"Set {period} en juego: {home_name} vs {away_name} | marcador por sets: {' - '.join(scores)}",
                            score_home=None,
                            score_away=None,
                            clock=status.get("displayClock"),
                            impact="medium",
                        ))
        return results
