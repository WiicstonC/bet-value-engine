import re
from datetime import datetime, timedelta, timezone

from app.models import Event, LiveIncident
from app.providers.odds_api import TheOddsAPIProvider


def _norm(value: str) -> str:
    value = re.sub(r"[^a-z0-9]", "", value.lower())
    for token in ("footballclub", "basketballclub", "fc", "cf", "afc", "bc", "club"):
        value = value.replace(token, "")
    return value


def match_incident(provider: TheOddsAPIProvider, incident: LiveIncident) -> Event | None:
    now = datetime.now(timezone.utc)
    events = provider.upcoming_events(incident.sport, now - timedelta(hours=8), now + timedelta(hours=1))
    home = _norm(incident.home)
    away = _norm(incident.away)
    exact = [event for event in events if _norm(event.home) == home and _norm(event.away) == away]
    if exact:
        return min(exact, key=lambda event: abs((event.start_time - incident.occurred_at).total_seconds()))
    partial = [event for event in events if (home in _norm(event.home) or _norm(event.home) in home) and (away in _norm(event.away) or _norm(event.away) in away)]
    if partial:
        return min(partial, key=lambda event: abs((event.start_time - incident.occurred_at).total_seconds()))
    return None
