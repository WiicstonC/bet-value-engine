from typing import Mapping


DEFAULT_WEIGHTS = {
    "statistics": 0.25,
    "edge": 0.20,
    "form": 0.15,
    "context": 0.15,
    "market": 0.10,
    "data_quality": 0.10,
    "uncertainty": 0.05,
}


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(value, maximum))


def calculate_confidence(
    inputs: Mapping[str, float] | None = None,
) -> float:
    """
    Calcula Confidence Score de 0 a 100.

    Los inputs representan factores normalizados entre 0 y 1.

    Si un factor no se proporciona, utilizamos 0.5 como valor neutral.
    """

    values = inputs or {}

    score = 0.0

    for factor, weight in DEFAULT_WEIGHTS.items():
        value = values.get(factor, 0.5)

        value = clamp(float(value))

        score += value * weight

    return round(score * 100, 2)


def confidence_label(confidence: float) -> str:

    if confidence >= 90:
        return "EXCEPTIONAL"

    if confidence >= 80:
        return "HIGH"

    if confidence >= 70:
        return "INTERESTING"

    if confidence >= 60:
        return "DOUBTFUL"

    return "LOW"
