from app.core.probability_engine import estimate_consensus_probability, probability_edge, probability_quality


def test_consensus_is_robust_to_one_outlier():
    estimate = estimate_consensus_probability([0.70, 0.71, 0.69, 0.95])
    assert 0.68 <= estimate.probability <= 0.72
    assert estimate.sample_size == 4
    assert estimate.confidence > 0


def test_probability_edge_is_probability_minus_implied():
    assert abs(probability_edge(0.60, 2.0) - 0.10) < 1e-9


def test_probability_quality_rewards_agreement_and_sample_size():
    strong = probability_quality(5, 0.005)
    weak = probability_quality(2, 0.08)
    assert strong > weak
