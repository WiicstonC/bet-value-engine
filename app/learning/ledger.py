from __future__ import annotations

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


def _key(row: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(row.get("event_id", "")),
        str(row.get("market", "")),
        str(row.get("selection", "")),
        str(row.get("line", "")),
    )


def register_candidate(candidate: Candidate) -> tuple[bool, str]:
    """Register a prediction for paper tracking and future calibration.

    This deliberately does not place a real wager. It records the exact
    probability/price snapshot so the engine can later compare its prediction
    with the actual result and calibrate itself.
    """
    rows = _read()
    key = (
        candidate.event.id,
        candidate.quote.market,
        candidate.quote.selection,
        str(candidate.quote.line),
    )
    if any(_key(row) == key and row.get("status") in {"pending", "won", "lost", "void"} for row in rows):
        return False, "Ese pronóstico ya está registrado."

    rows.append(
        {
            "prediction_id": f"{candidate.event.id}:{candidate.quote.market}:{candidate.quote.selection}:{candidate.quote.line}",
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
            "status": "pending",
            "outcome": None,
            "resolved_at": None,
            "resolution_source": None,
        }
    )
    _write(rows)
    return True, "Pronóstico registrado para seguimiento."


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
        buckets.append({
            "range": f"{low}-{high}%",
            "count": len(group),
            "predicted": sum(float(r.get("model_probability", 0)) for r in group) / len(group),
            "actual": wins / len(group),
            "error": (wins / len(group)) - (sum(float(r.get("model_probability", 0)) for r in group) / len(group)),
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
