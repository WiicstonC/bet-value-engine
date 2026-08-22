from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from statistics import median


@dataclass(frozen=True)
class ProbabilityEstimate:
    probability: float
    confidence: float
    sample_size: int
    dispersion: float
    method: str


def _clip(value: float, low: float = 0.001, high: float = 0.999) -> float:
    return max(low, min(high, value))


def estimate_consensus_probability(
    probabilities: list[float],
    *,
    prior: float | None = None,
) -> ProbabilityEstimate:
    """Estimate a market probability from independent no-vig probabilities.

    This is deliberately conservative: the engine does not claim certainty.
    With few books or high disagreement it shrinks the estimate toward the
    prior. A later statistical model can supply a sport/market-specific prior.
    """
    clean = [_clip(float(p)) for p in probabilities if 0.0 < float(p) < 1.0]
    if not clean:
        base = _clip(prior if prior is not None else 0.5)
        return ProbabilityEstimate(base, 0.0, 0, 1.0, "prior")

    center = median(clean)
    mean = sum(clean) / len(clean)
    dispersion = sqrt(sum((p - mean) ** 2 for p in clean) / len(clean))
    n_factor = min(len(clean) / 5.0, 1.0)
    agreement = max(0.0, 1.0 - min(dispersion * 6.0, 1.0))
    weight = n_factor * agreement

    if prior is None:
        probability = center
        method = "de-vig median consensus"
    else:
        prior_value = _clip(prior)
        probability = center * weight + prior_value * (1.0 - weight)
        method = "consensus + statistical prior"

    confidence = 100.0 * (0.35 + 0.65 * weight)
    return ProbabilityEstimate(
        probability=_clip(probability),
        confidence=confidence,
        sample_size=len(clean),
        dispersion=dispersion,
        method=method,
    )


def probability_edge(probability: float, odds: float) -> float:
    """Expected probability advantage versus the target bookmaker price."""
    if odds <= 1.0:
        return -1.0
    return _clip(probability) - (1.0 / odds)


def probability_quality(sample_size: int, dispersion: float) -> float:
    """0..1 quality score used to decide whether a signal deserves attention."""
    sample_factor = min(max(sample_size, 0) / 5.0, 1.0)
    agreement = max(0.0, 1.0 - min(dispersion * 6.0, 1.0))
    return 0.45 * sample_factor + 0.55 * agreement
