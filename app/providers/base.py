from abc import ABC, abstractmethod
from datetime import datetime

from app.models import Event, MarketQuote


class SportsProvider(ABC):
    @abstractmethod
    def upcoming_events(self, sport: str, start: datetime, end: datetime) -> list[Event]:
        raise NotImplementedError

    @abstractmethod
    def quotes(self, event: Event, markets: list[str]) -> list[MarketQuote]:
        raise NotImplementedError
