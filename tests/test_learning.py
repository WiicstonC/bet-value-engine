from datetime import datetime, timezone

from app.learning import ledger
from app.models import Candidate, Event, MarketQuote


def _candidate() -> Candidate:
    event = Event(
        id="event-learning-1",
        sport="football",
        competition="soccer_epl",
        home="Home FC",
        away="Away FC",
        start_time=datetime.now(timezone.utc),
    )
    quote = MarketQuote(
        event_id=event.id,
        market="h2h",
        selection="Home FC",
        odds=1.80,
        bookmaker="Betano",
        updated_at=datetime.now(timezone.utc),
    )
    return Candidate(
        event=event,
        quote=quote,
        model_probability=0.62,
        implied_probability=1 / 1.80,
        edge=0.0644,
        expected_value=0.116,
        confidence=78,
        decision="value",
        consensus_bookmakers=5,
        consensus_dispersion=0.02,
    )


def test_offer_then_register(monkeypatch, tmp_path):
    monkeypatch.setattr(ledger, "LEDGER_PATH", tmp_path / "predictions.json")
    candidate = _candidate()
    prediction_id = ledger.offer_candidate(candidate)
    assert prediction_id
    ok, _ = ledger.register_offer(prediction_id)
    assert ok
    assert len(ledger.pending()) == 1
    ok, _ = ledger.register_offer(prediction_id)
    assert not ok
