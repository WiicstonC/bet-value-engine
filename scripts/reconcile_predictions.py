from __future__ import annotations

from datetime import datetime, timezone

from app.alerts.telegram import TelegramAlertSender
from app.learning.ledger import pending, resolve_prediction, stats
from app.models import Event
from app.providers.odds_api import TheOddsAPIProvider


def main() -> None:
    sender = TelegramAlertSender()
    rows = pending()
    if not rows:
        print("No hay predicciones pendientes.")
        return

    provider = TheOddsAPIProvider()
    resolved = []
    for row in rows:
        try:
            event = Event(
                id=row["event_id"],
                sport=row["sport"],
                competition=row["competition"],
                home=row["home"],
                away=row["away"],
                start_time=datetime.fromisoformat(row["start_time"]),
            )
            if event.start_time > datetime.now(timezone.utc):
                continue
            score = provider.completed_event(event)
            if not score:
                continue
            status = provider.settle_score_market(row, score)
            if status is None:
                continue
            home_score = next((x.get("score") for x in score.get("scores", []) if x.get("name") == row["home"]), "?")
            away_score = next((x.get("score") for x in score.get("scores", []) if x.get("name") == row["away"]), "?")
            outcome = f"{row['home']} {home_score} - {away_score} {row['away']}"
            if resolve_prediction(row["prediction_id"], status, "Odds API scores", outcome):
                resolved.append((row, status, outcome))
        except Exception as exc:
            print(f"No se pudo resolver {row.get('prediction_id')}: {exc}")

    if resolved and sender.enabled:
        lines = ["🧠 RESULTADOS DEL MOTOR", ""]
        for row, status, outcome in resolved:
            icon = "🟢" if status == "won" else "🔴" if status == "lost" else "⚪"
            lines.extend([
                f"{icon} {row['home']} vs {row['away']}",
                f"{row['market']} | {row['selection']} {row['line'] if row['line'] is not None else ''}",
                f"Predicción: {float(row['model_probability']):.1%} | {outcome}",
                "",
            ])
        data = stats()
        hit = f"{data['hit_rate']:.1%}" if data['hit_rate'] is not None else "—"
        lines.append(f"📐 Hit rate acumulado: {hit}")
        lines.append("El histórico se usará para calibrar futuras probabilidades.")
        sender.send("\n".join(lines))

    print(f"Predicciones resueltas: {len(resolved)}")
    print(f"Estado: {stats()}")


if __name__ == "__main__":
    main()
