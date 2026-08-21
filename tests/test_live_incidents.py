from datetime import datetime, timezone

from app.live_incidents import LiveIncidentState
from app.models import LiveIncident
from app.providers.espn_live import ESPNLiveProvider


def incident(kind="red_card"):
    return LiveIncident(
        id="abc",
        event_id="event",
        sport="football",
        competition="soccer_epl",
        home="Arsenal",
        away="Chelsea",
        occurred_at=datetime.now(timezone.utc),
        kind=kind,
        description="Player sent off",
        impact="critical",
    )


def test_espn_classifies_red_card_as_critical():
    assert ESPNLiveProvider._classify("Player sent off after red card", "football") == ("red_card", "critical")


def test_incident_state_deduplicates():
    state = LiveIncidentState(path="/tmp/bet-value-engine-test-incidents.json")
    item = incident()
    assert state.new(item) is True
    assert state.new(item) is False
