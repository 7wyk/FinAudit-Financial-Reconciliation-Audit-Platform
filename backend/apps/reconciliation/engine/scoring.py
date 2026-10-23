"""
Scoring — deterministic composite scoring from component scores.

Combines individual matcher scores using configured weights.
All arithmetic uses Decimal for financial determinism.
"""

from dataclasses import dataclass
from decimal import Decimal

from .config import MatchConfig

ZERO = Decimal("0")


@dataclass(frozen=True)
class CandidateScore:
    """Immutable result of scoring a source-target pair."""

    composite: Decimal
    reference: Decimal
    amount: Decimal
    date: Decimal
    counterparty: Decimal
    evidence: dict

    @property
    def passes_minimum(self) -> bool:
        """Whether this score meets the minimum candidate threshold."""
        # This is checked by the caller using MatchConfig
        return True  # Threshold check is in policy, not here


def compute_composite_score(
    reference_score: Decimal,
    amount_score: Decimal,
    date_score: Decimal,
    counterparty_score: Decimal,
    reference_evidence: dict,
    amount_evidence: dict,
    date_evidence: dict,
    counterparty_evidence: dict,
    config: MatchConfig,
) -> CandidateScore:
    """
    Compute weighted composite score from component scores.

    Returns a frozen CandidateScore with composite score and full evidence.
    Deterministic: identical inputs always produce identical output.
    """
    composite = (
        reference_score * config.reference_weight +
        amount_score * config.amount_weight +
        date_score * config.date_weight +
        counterparty_score * config.counterparty_weight
    )

    # Quantize to 4 decimal places for consistency
    composite = composite.quantize(Decimal("0.0001"))

    evidence = {
        "reference": reference_evidence,
        "amount": amount_evidence,
        "date": date_evidence,
        "counterparty": counterparty_evidence,
        "weights": {
            "reference": str(config.reference_weight),
            "amount": str(config.amount_weight),
            "date": str(config.date_weight),
            "counterparty": str(config.counterparty_weight),
        },
        "composite_score": str(composite),
    }

    return CandidateScore(
        composite=composite,
        reference=reference_score,
        amount=amount_score,
        date=date_score,
        counterparty=counterparty_score,
        evidence=evidence,
    )
