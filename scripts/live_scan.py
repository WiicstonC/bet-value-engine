from app.alerts.manager import AlertManager
from app.alerts.telegram import TelegramAlertSender
from app.config import DEFAULT_CONFIG
from app.engine.scanner import Scanner
from app.live_analyzer import analyze_after_incident
from app.live_incidents import LiveIncidentState
from app.live_state import LiveState
from app.live_match import match_incident
from app.providers.espn_live import ESPNLiveProvider
from app.providers.odds_api import TheOddsAPIProvider


def main() -> None:
    config = DEFAULT_CONFIG
    incident_provider = ESPNLiveProvider()
    odds_provider = TheOddsAPIProvider()
    scanner = Scanner(odds_provider, config)
    incident_state = LiveIncidentState()
    odds_state = LiveState()

    fresh_incidents = []
    for sport in config.watchlist.sports:
        for incident in incident_provider.incidents(sport):
            if incident.impact in {"critical", "high", "medium"} and incident_state.new(incident):
                fresh_incidents.append(incident)

    candidates = []
    triggered = []
    for incident in fresh_incidents:
        event = match_incident(odds_provider, incident)
        if not event:
            print(f"No Odds API match for incident: {incident.description}")
            continue
        triggered.append((incident, event))
        try:
            candidates.extend(analyze_after_incident(odds_provider, scanner, event, incident, config))
        except Exception as exc:
            print(f"Incident analysis error {event.home} vs {event.away}: {exc}")

    alerts = []
    for candidate in candidates:
        should_alert, shock = odds_state.update_candidate(candidate, shock_percent=config.live.price_shock_percent)
        if should_alert:
            alerts.append((candidate, shock))

    incident_state.prune()
    incident_state.save()
    odds_state.save()

    print("=== BET VALUE LIVE INCIDENT SCANNER ===")
    print(f"Sports: {', '.join(config.watchlist.sports)}")
    print(f"Fresh live incidents: {len(fresh_incidents)}")
    print(f"Incidents matched to Odds API events: {len(triggered)}")
    print(f"Candidates after incident: {len(candidates)}")
    print(f"Live alerts: {len(alerts)}")
    print(f"API key activa: {odds_provider.active_key_number}")
    print(f"Failover de API keys: {odds_provider.failover_count}")
    if odds_provider.last_quota_remaining is not None:
        print(f"Odds API credits restantes: {odds_provider.last_quota_remaining}")
    if odds_provider.last_quota_used is not None:
        print(f"Odds API credits usados: {odds_provider.last_quota_used}")
    if odds_provider.last_quota_last is not None:
        print(f"Costo de la última consulta: {odds_provider.last_quota_last}")

    manager = AlertManager(TelegramAlertSender(), config)
    sent = 0
    for candidate, shock in alerts:
        incident_text = next((incident.description for incident, event in triggered if event.id == candidate.event.id), None)
        if manager.sender.send(manager.sender_message if False else __import__('app.alerts.manager', fromlist=['format_live_candidate']).format_live_candidate(candidate, config.timezone, incident_text)):
            sent += 1
        if sent >= config.live.max_alerts_per_run:
            break
    print(f"Alertas Telegram enviadas: {sent}")

    for incident, event in triggered:
        print(f"⚡ {incident.kind.upper()} | {event.home} vs {event.away} | {incident.description}")


if __name__ == "__main__":
    main()
