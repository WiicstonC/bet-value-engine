from datetime import datetime, timezone

from app.analysis.preanalysis import generate_preanalysis
from app.models import Event


def test_preanalysis_without_openai_key_returns_shortlist(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    events = [
        Event(
            id="1",
            sport="tennis",
            competition="tennis_atp_cincinnati_open",
            home="Player A",
            away="Player B",
            start_time=datetime.now(timezone.utc),
        )
    ]
    result = generate_preanalysis(events, max_events=1)
    assert "1" in result
    assert "vigilar" in result["1"]
