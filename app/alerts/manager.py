from app.models import Candidate
from app.alerts.telegram import TelegramAlertSender


def format_candidate(candidate: Candidate) -> str:
    event = candidate.event
    quote = candidate.quote
    line = f" {quote.line}" if quote.line is not None else ""

    return (
        "🎯 BET VALUE ALERT\n\n"
        f"{event.sport.upper()} — {event.home} vs {event.away}\n"
        f"Market: {quote.market}{line}\n"
        f"Selection: {quote.selection}\n"
        f"Odds: {quote.odds:.2f}\n"
        f"Model probability: {candidate.model_probability:.2%}\n"
        f"Market probability: {candidate.implied_probability:.2%}\n"
        f"Edge: {candidate.edge:.2%}\n"
        f"EV: {candidate.expected_value:.2%}\n"
        f"Confidence: {candidate.confidence:.1f}/100\n"
        f"Decision: {candidate.decision}"
    )


class AlertManager:
    def __init__(self, sender: TelegramAlertSender):
        self.sender = sender

    def notify(self, candidates: list[Candidate]) -> int:
        sent = 0
        for candidate in candidates:
            if self.sender.send(format_candidate(candidate)):
                sent += 1
        return sent
