from datetime import datetime, timezone

from app.alerts.manager import competition_flag, deep_button, format_daily_digest
from app.config import DEFAULT_CONFIG
from app.models import Event


def event(competition: str) -> Event:
    return Event(
        id="abc123",
        sport="football",
        competition=competition,
        home="Equipo A",
        away="Equipo B",
        start_time=datetime(2026, 8, 22, 18, 0, tzinfo=timezone.utc),
    )


def test_competition_flag_for_colombia():
    assert competition_flag(event("soccer_colombia_primera_a")) == "🇨🇴"


def test_deep_button_contains_no_more_than_64_bytes():
    markup = deep_button(event("soccer_colombia_primera_a"))
    button = markup["inline_keyboard"][0][0]
    assert button["text"] == "🔬 Analizar a fondo"
    assert len(button["callback_data"].encode("utf-8")) <= 64


def test_daily_digest_hides_event_id_and_adds_deep_button():
    current = event("soccer_colombia_primera_a")
    messages, markups = format_daily_digest(
        [current],
        DEFAULT_CONFIG.timezone,
        max_events=45,
        preanalysis={current.id: "🧠 Partido para estudiar."},
    )
    card_index = next(i for i, message in enumerate(messages) if "Partido para estudiar" in message)
    assert current.id not in messages[card_index]
    assert markups[card_index]["inline_keyboard"][0][0]["callback_data"].startswith("deep|football|")
