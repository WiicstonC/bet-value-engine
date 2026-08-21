import json
import os
from datetime import datetime

import httpx

from app.models import Event


MODEL = os.getenv("OPENAI_PREANALYSIS_MODEL", "gpt-5.6-luna")


def _fallback(event: Event) -> str:
    sport = event.sport.lower()
    if sport == "tennis":
        return "🎾 Partido para vigilar. Antes de tocar ganador conviene revisar servicio, devolución, superficie y mercados de juegos/sets; la cuota decidirá si existe valor."
    if sport == "nba":
        return "🏀 Partido para vigilar. El mercado de ganador no será nuestra única opción: si el juego es parejo, conviene buscar puntos, rebotes, asistencias o triples después de revisar contexto y cuotas."
    return "⚽ Partido para vigilar. No asumimos ganador todavía; primero conviene revisar contexto, ritmo, goles, córners y tarjetas para encontrar el mercado con mayor probabilidad."


def generate_preanalysis(events: list[Event], max_events: int = 10) -> dict[str, str]:
    """Generate a qualitative shortlist without spending Odds API credits.

    The model may use web search for current context. Odds are deliberately not
    included: this stage decides which events deserve an expensive market scan.
    """
    if not events:
        return {}

    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return {event.id: _fallback(event) for event in events[:max_events]}

    payload_events = [
        {
            "id": event.id,
            "sport": event.sport,
            "competition": event.competition,
            "home": event.home,
            "away": event.away,
            "start_utc": event.start_time.isoformat(),
        }
        for event in events
    ]

    prompt = f"""
Eres el analista principal de un motor privado de apuestas deportivas. Tu trabajo en esta etapa NO es recomendar una apuesta ni inventar probabilidades. Debes hacer un preanálisis cualitativo para decidir qué partidos merecen gastar créditos en una consulta profunda de mercados.

Hoy es {datetime.utcnow().date().isoformat()}.
Deportes vigilados: tenis, fútbol y NBA.

Reglas:
- Investiga en la web solo si ayuda a conocer contexto actual: forma reciente, lesiones/bajas, rotaciones, superficie, calendario, descanso, noticias relevantes y situación competitiva.
- No uses cuotas todavía y no inventes cuotas.
- No afirmes datos que no puedas verificar.
- No te limites a ganador. Señala qué familias de mercados podrían ser interesantes: ganador, handicap/spread, juegos/sets, aces/dobles faltas, goles, córners, tarjetas, tiros, tiros a puerta, puntos, rebotes, asistencias, triples, etc., según deporte.
- Si no ves una razón clara para estudiar un evento, dilo.
- Selecciona como máximo {max_events} eventos de mayor interés para un análisis profundo.
- La salida debe ser JSON válido con la clave "events". Cada elemento debe tener: id, priority (1-100), verdict ("ESTUDIAR" o "PASAR"), preanalysis (máximo 420 caracteres), markets_to_check (lista de hasta 5 mercados), reason (máximo 220 caracteres).

Eventos disponibles:
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
        response = httpx.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=body,
            timeout=90,
        )
        response.raise_for_status()
        data = response.json()
        text = data.get("output_text", "")
        parsed = json.loads(text)
        result: dict[str, str] = {}
        for item in parsed.get("events", []):
            if item.get("verdict") != "ESTUDIAR":
                continue
            event_id = str(item.get("id", ""))
            if event_id not in {event.id for event in events}:
                continue
            markets = ", ".join(item.get("markets_to_check", [])[:5])
            result[event_id] = (
                f"🧠 {item.get('preanalysis', '').strip()}\n"
                f"Mercados a revisar: {markets or 'descubrir en análisis profundo'}\n"
                f"Motivo: {item.get('reason', '').strip()}"
            )
        return result
    except Exception as exc:
        print(f"AI preanalysis unavailable: {exc}")
        return {event.id: _fallback(event) for event in events[:max_events]}
