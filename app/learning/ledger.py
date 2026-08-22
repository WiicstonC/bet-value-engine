from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.models import Candidate


LEDGER_PATH = Path(__file__).resolve().parents[2] / "data" / "predictions.json"


def _read() -> list[dict[str, Any]]:
    if not LEDGER_PATH.exists():
        return []
    try:
        data = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def _write(rows: list[dict[str, Any]]) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = LEDGER_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(LEDGER_PATH)


def _prediction_id(candidate: Candidate) -> str:
    raw = f"{candidate.event.id}|{candidate.quote.market}|{candidate.quote.selection}|{candidate.quote.line}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(row.get("event_id", "")),
        str(row.get("market", "")),
        str(row.get("selection", "")),
        str(row.get("line", "")),
    )


def _candidate_row(candidate: Candidate, status: str) -> dict[str, Any]:
    return {
        "prediction_id": _prediction_id(candidate),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "event_id": candidate.event.id,
        "sport": candidate.event.sport,
        "competition": candidate.event.competition,
        "home": candidate.event.home,
        "away": candidate.event.away,
        "start_time": candidate.event.start_time.isoformat(),
        "market": candidate.quote.market,
        "selection": candidate.quote.selection,
        "line": candidate.quote.line,
        "odds": candidate.quote.odds,
        "bookmaker": candidate.quote.bookmaker,
        "model_probability": candidate.model_probability,
        "implied_probability": candidate.implied_probability,
        "edge": candidate.edge,
        "expected_value": candidate.expected_value,
        "confidence": candidate.confidence,
        "consensus_bookmakers": candidate.consensus_bookmakers,
        "consensus_dispersion": candidate.consensus_dispersion,
        "status": status,
        "outcome": None,
        "resolved_at": None,
        "resolution_source": None,
    }


def offer_candidate(candidate: Candidate) -> str:
    """Persist a deep-analysis offer so Telegram can render a short callback."""
    rows = _read()
    key = _key(_candidate_row(candidate, "offered"))
    for row in rows:
        if _key(row) == key and row.get("status") in {"offered", "pending", "won", "lost", "void"}:
            return str(row["prediction_id"])
    row = _candidate_row(candidate, "offered")
    rows.append(row)
    _write(rows)
    return str(row["prediction_id"])


def register_offer(prediction_id: str) -> tuple[bool, str]:
    """Move an offered prediction into the learning set.

    This is paper tracking only; it never submits a wager to a bookmaker.
    """
    rows = _read()
    for row in rows:
        if row.get("prediction_id") == prediction_id:
            if row.get("status") == "pending":
                return False, "Ese pronóstico ya está en seguimiento."
            if row.get("status") in {"won", "lost", "void"}:
                return False, "Ese pronóstico ya fue cerrado."
            if row.get("status") == "offered":
                row["status"] = "pending"
                row["registered_at"] = datetime.now(timezone.utc).isoformat()
                _write(rows)
                return True, "Pronóstico registrado. Quedará guardado para aprender del resultado."
    return False, "No encontré ese pronóstico; puede haber expirado."


def register_candidate(candidate: Candidate) -> tuple[bool, str]:
    prediction_id = offer_candidate(candidate)
    return register_offer(prediction_id)


def pending() -> list[dict[str, Any]]:
    return [row for row in _read() if row.get("status") == "pending"]


def stats() -> dict[str, Any]:
    rows = _read()
    resolved = [r for r in rows if r.get("status") in {"won", "lost"}]
    wins = sum(r.get("status") == "won" for r in resolved)
    losses = sum(r.get("status") == "lost" for r in resolved)
    return {
        "total": len(rows),
        "pending": sum(r.get("status") == "pending" for r in rows),
        "resolved": len(resolved),
        "wins": wins,
        "losses": losses,
        "hit_rate": wins / len(resolved) if resolved else None,
        "calibration": calibration_buckets(resolved),
    }


def calibration_buckets(rows: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    rows = rows if rows is not None else [r for r in _read() if r.get("status") in {"won", "lost"}]
    buckets: list[dict[str, Any]] = []
    for low in range(50, 100, 5):
        high = low + 5
        group = [r for r in rows if low <= float(r.get("model_probability", 0)) * 100 < high]
        if not group:
            continue
        wins = sum(r.get("status") == "won" for r in group)
        predicted = sum(float(r.get("model_probability", 0)) for r in group) / len(group)
        actual = wins / len(group)
        buckets.append({
            "range": f"{low}-{high}%",
            "count": len(group),
            "predicted": predicted,
            "actual": actual,
            "error": actual - predicted,
        })
    return buckets


def resolve_prediction(prediction_id: str, status: str, source: str, outcome: str | None = None) -> bool:
    rows = _read()
    changed = False
    for row in rows:
        if row.get("prediction_id") == prediction_id and row.get("status") == "pending":
            row["status"] = status
            row["outcome"] = outcome
            row["resolved_at"] = datetime.now(timezone.utc).isoformat()
            row["resolution_source"] = source
            changed = True
            break
    if changed:
        _write(rows)
    return changed
