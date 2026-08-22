from collections import defaultdict

from app.core.probability_engine import estimate_consensus_probability
from app.models import MarketQuote


def _normalization_line(quote: MarketQuote) -> float | None:
    if quote.line is None:
        return None
    if quote.market.lower() == "spreads":
        return abs(quote.line)
    return quote.line


def _is_excluded(bookmaker: str, excluded: str) -> bool:
    bookmaker = bookmaker.lower().strip()
    excluded = excluded.lower().strip()
    if excluded == "betano":
        return "betano" in bookmaker
    return bookmaker == excluded or excluded in bookmaker


def consensus_probabilities(
    quotes: list[MarketQuote],
    excluded_bookmaker: str = "Betano",
) -> dict[tuple[str, float | None, str], tuple[float, int, float]]:
    """Build a conservative de-vigged probability consensus.

    Returns key -> (probability, bookmaker_count, dispersion).
    The target bookmaker is excluded so its own price does not manufacture
    the reference probability used to calculate edge.
    """
    grouped: dict[tuple[str, float | None, str], list[float]] = defaultdict(list)
    by_bookmaker: dict[tuple[str, float | None], dict[tuple[str, str], float]] = defaultdict(dict)

    for quote in quotes:
        if _is_excluded(quote.bookmaker, excluded_bookmaker):
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
        estimate = estimate_consensus_probability(probabilities)
        result[key] = (estimate.probability, estimate.sample_size, estimate.dispersion)

    return result
