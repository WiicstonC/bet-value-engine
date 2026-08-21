import json
import os
import time
from datetime import datetime

import httpx

from app.models import Event


MODEL = os.getenv("OPENAI_PREANALYSIS_MODEL", "gpt-5.6-luna")


def _fallback(event: Event) -> str:
    sport = event.sport.lower()
    if sport == "tennis":
        return "🎾 VIGILAR. Antes de elegir ganador, revisar superficie, forma reciente, servicio/devolución, fatiga y H2H. Si el partido es parejo, juegos/sets, aces o dobles faltas pueden ofrecer mejor valor."
    if sport == "nba":
        return "🏀 VIGILAR. No limitarse al ganador: revisar ritmo, lesiones, minutos y matchup. Si el resultado es cerrado, puntos, rebotes, asistencias y triples pueden ser mercados más interesantes."
    return "⚽ VIGILAR. No asumir ganador. Revisar forma, bajas, local/visitante y contexto; después comparar goles, córners, tarjetas, tiros y tiros a puerta para encontrar el mercado con mejor perfil."


def _output_text(data: dict) -> str:
    parts = []
    for item in data.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                parts.append(content["text"])
    return "\n".join(parts).strip()


def _request(body: dict, api_key: str) -> httpx.Response:
    last: httpx.Response | None = None
    for attempt in range(3):
        response = httpx.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=body,
            timeout=90,
        )
        last = response
        if response.status_code != 429:
            response.raise_for_status()
            return response
        retry_after = response.headers.get("retry-after")
        try:
            delay = min(max(float(retry_after), 2.0), 20.0) if retry_after else 4.0 * (attempt + 1)
        except ValueError:
            delay = 4.0 * (attempt + 1)
        time.sleep(delay)
    assert last is not None
    last.raise_for_status()
    return last


def generate_preanalysis(events: list[Event], max_events: int = 10) -> dict[str, str]:
    """Generate a qualitative shortlist without spending Odds API credits."""
    if not events:
        return {}

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return {event.id: _fallback(event) for event in events[:max_events]}

    valid_ids = {event.id for event in events}
    # Send only a bounded event list to the AI; the complete agenda is still sent to Telegram.
    payload_events = [
        {"id": e.id, "sport": e.sport, "competition": e.competition, "home": e.home, "away": e.away, "start_utc": e.start_time.isoformat()}
        for e in events[:min(len(events), 30)]
    ]

    prompt = f"""
Eres el analista principal de un motor privado de apuestas deportivas. En esta etapa NO recomiendas una apuesta ni inventas probabilidades. Haces un preanálisis cualitativo para decidir qué partidos merecen gastar créditos en una consulta profunda de mercados.

Hoy es {datetime.utcnow().date().isoformat()}.
Reglas:
- Usa web search para comprobar contexto actual cuando sea útil: forma reciente, lesiones/bajas, rotaciones, superficie, calendario, descanso, noticias y situación competitiva.
- No uses cuotas todavía y no inventes cuotas.
- No afirmes datos que no puedas verificar.
- No te limites a ganador. Señala familias de mercados potencialmente interesantes: ganador, handicap/spread, juegos/sets, aces/dobles faltas, goles, córners, tarjetas, tiros, tiros a puerta, puntos, rebotes, asistencias, triples, etc.
- Si no existe una razón clara para estudiar un evento, marca PASAR.
- Selecciona como máximo {max_events} eventos.
- Devuelve JSON con clave events. Cada elemento: id, priority 1-100, verdict ESTUDIAR/PASAR, preanalysis <=420 caracteres, markets_to_check <=5, reason <=220 caracteres.

EVENTOS:
{json.dumps(payload_events, ensure_ascii=False, indent=2)}
"""

    body = {
        "model": MODEL,
        "tools": [{"type": "web_search", "search_context_size": "low"}],
        "input": prompt,
        "store": False,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "sports_preanalysis",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "events": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "id": {"type": "string"},
                                    "priority": {"type": "number"},
                                    "verdict": {"type": "string"},
                                    "preanalysis": {"type": "string"},
                                    "markets_to_check": {"type": "array", "items": {"type": "string"}},
                                    "reason": {"type": "string"},
                                },
                                "required": ["id", "priority", "verdict", "preanalysis", "markets_to_check", "reason"],
                                "additionalProperties": False,
                            },
                        }
                    },
                    "required": ["events"],
                    "additionalProperties": False,
                },
            }
        },
    }

    try:
        response = _request(body, api_key)
        parsed = json.loads(_output_text(response.json()))
        result: dict[str, str] = {}
        for item in parsed.get("events", []):
            if item.get("verdict") != "ESTUDIAR":
                continue
            event_id = str(item.get("id", ""))
            if event_id not in valid_ids:
                continue
            markets = ", ".join(item.get("markets_to_check", [])[:5])
            result[event_id] = (
                f"🧠 {item.get('preanalysis', '').strip()}\n"
                f"🔥 Mercados a vigilar: {markets or 'descubrir en análisis profundo'}\n"
                f"Motivo: {item.get('reason', '').strip()}"
            )
        return result
    except Exception as exc:
        print(f"AI preanalysis unavailable after retries: {exc}")
        return {event.id: _fallback(event) for event in events[:max_events]}
