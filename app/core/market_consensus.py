from collections import defaultdict

from app.models import MarketQuote


def _key(quote: MarketQuote) -> tuple[str, float | None, str]:
    return (quote.market.lower(), quote.line, quote.selection.lower())


def consensus_probabilities(quotes: list[MarketQuote], excluded_bookmaker: str = "Betano") -> dict[tuple[str, float | None, str], tuple[float, int, float]]:
    """Build a de-vigged market consensus for each selection.

    Returns key -> (probability, bookmaker_count, dispersion).
    Dispersion is the population standard deviation of the bookmaker probabilities.
    """
    grouped: dict[tuple[str, float | None, str], list[float]] = defaultdict(list)
    by_bookmaker: dict[tuple[str, float | None], dict[str, float]] = defaultdict(dict)

    for quote in quotes:
        if quote.bookmaker.lower() == excluded_bookmaker.lower():
            continue
        if quote.odds <= 1:
            continue
        group = (quote.market.lower(), quote.line)
        by_bookmaker[group][quote.bookmaker.lower() + "|" + quote.selection.lower()] = 1.0 / quote.odds

    # Reconstruct one normalized probability per outcome for each bookmaker.
    for group, values in by_bookmaker.items():
        selections: dict[str, float] = {}
        for composite, probability in values.items():
            selection = composite.split("|", 1)[1]
            selections[selection] = probability
        total = sum(selections.values())
        if total <= 0:
            continue
        for selection, probability in selections.items():
            grouped[(group[0], group[1], selection)].append(probability / total)

    result: dict[tuple[str, float | None, str], tuple[float, int, float]] = {}
    for key, probabilities in grouped.items():
        if not probabilities:
            continue
        mean = sum(probabilities) / len(probabilities)
        variance = sum((p - mean) ** 2 for p in probabilities) / len(probabilities)
        result[key] = (mean, len(probabilities), variance ** 0.5)
    return result
