def implied_probability(odds: float) -> float:
    """
    Convierte una cuota decimal en probabilidad implícita.

    Ejemplo:
    2.00 -> 0.50
    1.50 -> 0.6667
    3.00 -> 0.3333
    """

    if odds <= 1:
        raise ValueError("La cuota debe ser mayor que 1.")

    return 1.0 / odds


def normalize_market_probabilities(probabilities: list[float]) -> list[float]:
    """
    Elimina aproximadamente el margen de la casa normalizando
    las probabilidades implícitas de un mercado.

    Ejemplo:
    [0.55, 0.50]
    suma = 1.05

    resultado:
    [0.5238, 0.4762]
    """

    if not probabilities:
        raise ValueError("Debe existir al menos una probabilidad.")

    if any(p <= 0 for p in probabilities):
        raise ValueError("Las probabilidades deben ser positivas.")

    total = sum(probabilities)

    if total <= 0:
        raise ValueError("La suma de probabilidades debe ser positiva.")

    return [p / total for p in probabilities]
