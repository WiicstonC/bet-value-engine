from datetime import datetime

from app.models import Event


def events_for_keys(provider, sport_keys: list[str], sport: str, start: datetime, end: datetime) -> list[Event]:
    """Fetch events only for explicitly selected competitions.

    This is used by Telegram so selecting Spain, England, NBA, etc. does not
    scan every competition in the catalog. The API's active-sports catalog is
    still handled by the provider without consuming an odds query.
    """
    events: list[Event] = []
    seen: set[str] = set()
    for sport_key in dict.fromkeys(sport_keys):
        try:
            data = provider._get(f"/sports/{sport_key}/events", {})
        except Exception as exc:
            print(f"No se pudo consultar {sport_key}: {exc}")
            continue
        if not isinstance(data, list):
            continue
        for item in data:
            try:
                start_time = datetime.fromisoformat(str(item["commence_time"]).replace("Z", "+00:00"))
                event_id = str(item["id"])
                if event_id in seen or not (start <= start_time <= end):
                    continue
                seen.add(event_id)
                events.append(Event(
                    id=event_id,
                    sport=sport,
                    competition=sport_key,
                    home=str(item["home_team"]),
                    away=str(item["away_team"]),
                    start_time=start_time,
                ))
            except (KeyError, TypeError, ValueError) as exc:
                print(f"Evento inválido en {sport_key}: {exc}")
    return sorted(events, key=lambda event: event.start_time)
