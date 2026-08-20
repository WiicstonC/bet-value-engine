from fastapi import FastAPI, HTTPException

from app.schemas import BetAnalysisRequest, BetAnalysisResponse
from app.core.probability import implied_probability
from app.core.value import (
    calculate_edge,
    calculate_expected_value,
    calculate_risk,
    classify_value,
)
from app.core.confidence import calculate_confidence


app = FastAPI(
    title="Bet Value Engine",
    description=(
        "Motor de análisis de valor para apuestas deportivas. "
        "No ejecuta apuestas automáticamente."
    ),
    version="0.1.1",
)


@app.get("/")
def root():
    return {
        "name": "Bet Value Engine",
        "version": "0.1.1",
        "status": "online",
        "message": "Value engine ready",
    }


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/analyze", response_model=BetAnalysisResponse)
def analyze_bet(request: BetAnalysisRequest):
    try:
        market_probability = implied_probability(request.odds)
        edge = calculate_edge(request.model_probability, market_probability)
        expected_value = calculate_expected_value(request.model_probability, request.odds)
        confidence = calculate_confidence(request.confidence_inputs)
        decision = classify_value(edge, expected_value)
        risk = calculate_risk(request.model_probability, edge, expected_value)

        reasons = []
        if edge > 0:
            reasons.append("La probabilidad del modelo supera la probabilidad implícita.")
        if expected_value > 0:
            reasons.append("El valor esperado es positivo.")
        if edge >= 0.10:
            reasons.append("Existe un edge significativo.")
        if confidence >= 80:
            reasons.append("El índice de confianza es alto.")
        if expected_value <= 0:
            reasons.append("El modelo no detecta valor esperado positivo.")

        return BetAnalysisResponse(
            sport=request.sport,
            market=request.market,
            selection=request.selection,
            odds=request.odds,
            implied_probability=round(market_probability, 6),
            model_probability=round(request.model_probability, 6),
            edge=round(edge, 6),
            expected_value=round(expected_value, 6),
            confidence=confidence,
            decision=decision,
            risk_level=risk,
            reasons=reasons,
        )

    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
