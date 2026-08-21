import json
from datetime import datetime, timezone
from pathlib import Path

from app.models import LiveIncident


class LiveIncidentState:
    def __init__(self, path: str = "data/live_incidents.json"):
        self.path = Path(path)
        self.seen: dict[str, str] = self._load()

    def _load(self) -> dict[str, str]:
        if not self.path.exists():
            return {}
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def new(self, incident: LiveIncident) -> bool:
        if incident.id in self.seen:
            return False
        self.seen[incident.id] = datetime.now(timezone.utc).isoformat()
        return True

    def prune(self, keep_days: int = 3) -> None:
        now = datetime.now(timezone.utc)
        kept: dict[str, str] = {}
        for key, value in self.seen.items():
            try:
                age = (now - datetime.fromisoformat(value)).total_seconds() / 86400
            except ValueError:
                age = 999
            if age <= keep_days:
                kept[key] = value
        self.seen = kept

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.seen, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
