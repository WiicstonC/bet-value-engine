import json
from datetime import datetime, timezone
from pathlib import Path

from app.models import Candidate


class LiveState:
    def __init__(self, path: str = "data/live_state.json"):
        self.path = Path(path)
        self.data: dict[str, dict] = self._load()

    def _load(self) -> dict[str, dict]:
        if not self.path.exists():
            return {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    @staticmethod
    def key(candidate: Candidate) -> str:
        q = candidate.quote
        return "|".join([
            candidate.event.id,
            q.market,
            q.selection,
            str(q.line),
            q.bookmaker,
        ])

    def update_candidate(self, candidate: Candidate, shock_percent: float, cooldown_minutes: int = 30) -> tuple[bool, float | None]:
        key = self.key(candidate)
        now = datetime.now(timezone.utc)
        previous = self.data.get(key, {})
        previous_odds = previous.get("odds")
        shock = None
        if isinstance(previous_odds, (int, float)) and previous_odds > 0:
            shock = abs(candidate.quote.odds - float(previous_odds)) / float(previous_odds) * 100

        last_alerted = previous.get("last_alerted")
        cooldown_ok = True
        if last_alerted:
            try:
                elapsed = (now - datetime.fromisoformat(last_alerted)).total_seconds() / 60
                cooldown_ok = elapsed >= cooldown_minutes
            except ValueError:
                pass

        should_alert = shock is None or shock >= shock_percent
        should_alert = should_alert and cooldown_ok

        self.data[key] = {
            "odds": candidate.quote.odds,
            "line": candidate.quote.line,
            "updated_at": now.isoformat(),
            "last_alerted": now.isoformat() if should_alert else last_alerted,
        }
        return should_alert, shock

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
