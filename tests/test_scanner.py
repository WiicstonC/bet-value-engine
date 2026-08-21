from datetime import datetime, timedelta, timezone

from app.config import DEFAULT_CONFIG
from app.engine.scanner import Scanner


class DummyProvider:
    pass


def test_betano_alias_matches_brand_title():
    scanner = Scanner(DummyProvider(), DEFAULT_CONFIG)
    assert scanner._bookmaker_matches("Betano (UK)", "Betano")
    assert not scanner._bookmaker_matches("BetVictor", "Betano")


def test_alert_window_uses_configured_targets():
    scanner = Scanner(DummyProvider(), DEFAULT_CONFIG)
    now = datetime.now(timezone.utc)
    assert scanner._in_alert_window(
        now + timedelta(minutes=10),
        now,
    )
    assert not scanner._in_alert_window(
        now + timedelta(minutes=25),
        now,
    )


def test_alert_mode_uses_h2h_before_kickoff():
    scanner = Scanner(DummyProvider(), DEFAULT_CONFIG)
    now = datetime.now(timezone.utc)
    assert scanner._markets_for_event(now + timedelta(minutes=60), now, True) == ["h2h"]
    assert scanner._markets_for_event(now + timedelta(minutes=10), now, True) == DEFAULT_CONFIG.watchlist.markets


def test_full_mode_keeps_all_configured_markets():
    scanner = Scanner(DummyProvider(), DEFAULT_CONFIG)
    now = datetime.now(timezone.utc)
    assert scanner._markets_for_event(now + timedelta(hours=12), now, False) == DEFAULT_CONFIG.watchlist.markets
