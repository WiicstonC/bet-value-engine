from collections import defaultdict

from app.models import MarketQuote


def _normalization_line(quote: MarketQuote) -> float | None:
    if quote.line is None:
        return None
    if quote.market.lower() == "spreads":
        return abs(quote.line)
    return quote.line


def consensus_probabilities(
    quotes: list[MarketQuote],
    excluded_bookmaker: str = "Betano",
) -> dict[tuple[str, float | None, str], tuple[float, int, float]]:
    """Build a de-vigged consensus across independent bookmakers.

    Returns key -> (probability, bookmaker_count, dispersion).
    For spreads, +X and -X are normalized together before de-vigging.
    """
    grouped: dict[tuple[str, float | None, str], list[float]] = defaultdict(list)
    by_bookmaker: dict[tuple[str, float | None], dict[tuple[str, str], float]] = defaultdict(dict)

    for quote in quotes:
        if quote.bookmaker.lower() == excluded_bookmaker.lower():
            continue
        if quote.odds <= 1:
            continue
        group = (quote.market.lower(), _normalization_line(quote))
        by_bookmaker[group][
            (quote.bookmaker.lower(), quote.selection.lower())
        ] = 1.0 / quote.odds

    for group, values in by_bookmaker.items():
        selections: dict[str, float] = {}
        for (_, selection), probability in values.items():
            selections[selection] = selections.get(selection, 0.0) + probability

        total = sum(selections.values())
        if total <= 0:
            continue

        for selection, probability in selections.items():
            grouped[(group[0], group[1], selection)].append(probability / total)

    result: dict[tuple[str, float | None, str], tuple[float, int, float]] = {}
    for key, probabilities in grouped.items():
        mean = sum(probabilities) / len(probabilities)
        variance = sum((p - mean) ** 2 for p in probabilities) / len(probabilities)
        result[key] = (mean, len(probabilities), variance ** 0.5)

    return result
