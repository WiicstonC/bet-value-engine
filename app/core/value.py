def calculate_edge(
    model_probability: float,
    market_probability: float,
) -> float:
    """
    Edge = probabilidad del modelo - probabilidad del mercado.
    """

    return model_probability - market_probability


def calculate_expected_value(
    model_probability: float,
    odds: float,
) -> float:
    """
    EV por unidad apostada.

    EV = (probabilidad * cuota) - 1

    Ejemplo:
    probabilidad = 0.60
    cuota = 2.00

    EV = 0.20
    """

    return (model_probability * odds) - 1.0


def classify_value(
    edge: float,
    expected_value: float,
) -> str:

    if expected_value <= 0:
        return "NO_VALUE"

    if edge >= 0.10 and expected_value >= 0.15:
        return "STRONG_VALUE"

    if edge >= 0.05 and expected_value >= 0.05:
        return "VALUE"

    return "WEAK_VALUE"


def calculate_risk(
    model_probability: float,
    edge: float,
    expected_value: float,
) -> str:

    if model_probability < 0.50:
        return "HIGH"

    if edge < 0.03:
        return "HIGH"

    if expected_value <= 0:
        return "HIGH"

    if edge < 0.05:
        return "MEDIUM"

    return "LOW"
