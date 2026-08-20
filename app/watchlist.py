from app.config import EngineConfig
from app.data_models import Event


def matches_watchlist(event: Event, config: EngineConfig) -> bool:
    watchlist = config.watchlist

    if watchlist.sports and event.sport.lower() not in {
        value.lower() for value in watchlist.sports
    }:
        return False

    competition_filters = {value.lower() for value in watchlist.competitions if value.strip()}
    team_filters = {value.lower() for value in watchlist.teams if value.strip()}

    if competition_filters and event.competition.lower() not in competition_filters:
        return False

    if team_filters:
        participants = {event.home.lower(), event.away.lower()}
        if not participants.intersection(team_filters):
            return False

    return True


def filter_events(events: list[Event], config: EngineConfig) -> list[Event]:
    return [event for event in events if matches_watchlist(event, config)]
