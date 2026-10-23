"""
Matching configuration — all tolerance and weight parameters.

Frozen dataclass ensures configuration is immutable once created,
guaranteeing deterministic behaviour across repeated runs.
"""

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class MatchConfig:
    """
    Immutable configuration for a reconciliation run.

    Weights must sum to 1.0 for normalized scoring.
    Tolerances define the maximum permitted deviation for a positive score.
    Thresholds control match/ambiguity classification.
    """

    # ── Component weights (must sum to 1.0) ──────────────────────────
    reference_weight: Decimal = Decimal("0.40")
    amount_weight: Decimal = Decimal("0.30")
    date_weight: Decimal = Decimal("0.20")
    counterparty_weight: Decimal = Decimal("0.10")

    # ── Tolerances ───────────────────────────────────────────────────
    # Amount: maximum absolute difference for full score
    amount_tolerance: Decimal = Decimal("0.01")
    # Amount: maximum for partial score (linear decay)
    amount_tolerance_upper: Decimal = Decimal("1.00")

    # Date: maximum day difference for full score
    date_tolerance_days: int = 0
    # Date: maximum day difference for partial score
    date_tolerance_days_upper: int = 3

    # ── Decision thresholds ──────────────────────────────────────────
    # Score >= match_threshold → auto-match
    match_threshold: Decimal = Decimal("0.85")
    # Score >= ambiguity_threshold (and < match_threshold) → candidate
    ambiguity_threshold: Decimal = Decimal("0.50")
    # Minimum score to keep a candidate at all
    minimum_candidate_score: Decimal = Decimal("0.30")

    # Maximum candidates per source transaction before flagging conflict
    max_candidates_before_conflict: int = 3

    def __post_init__(self):
        total = (
            self.reference_weight + self.amount_weight +
            self.date_weight + self.counterparty_weight
        )
        if total != Decimal("1.00"):
            raise ValueError(
                f"Component weights must sum to 1.00, got {total}"
            )

    def to_dict(self) -> dict:
        """Serialize to JSON-safe dict for persisting in ReconciliationRun.config."""
        return {
            "reference_weight": str(self.reference_weight),
            "amount_weight": str(self.amount_weight),
            "date_weight": str(self.date_weight),
            "counterparty_weight": str(self.counterparty_weight),
            "amount_tolerance": str(self.amount_tolerance),
            "amount_tolerance_upper": str(self.amount_tolerance_upper),
            "date_tolerance_days": self.date_tolerance_days,
            "date_tolerance_days_upper": self.date_tolerance_days_upper,
            "match_threshold": str(self.match_threshold),
            "ambiguity_threshold": str(self.ambiguity_threshold),
            "minimum_candidate_score": str(self.minimum_candidate_score),
            "max_candidates_before_conflict": self.max_candidates_before_conflict,
        }
