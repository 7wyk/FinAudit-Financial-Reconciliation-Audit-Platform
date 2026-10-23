"""
Matchers — individual component matchers for candidate generation.

Each matcher produces a component score in [0.0, 1.0] plus evidence metadata.
All use Decimal arithmetic for financial determinism.
"""

from datetime import date
from decimal import Decimal
from difflib import SequenceMatcher

from .config import MatchConfig

ZERO = Decimal("0")
ONE = Decimal("1")


def match_reference(
    source_ref: str,
    target_ref: str,
    source_norm_ref: str,
    target_norm_ref: str,
) -> tuple[Decimal, dict]:
    """
    Reference matching — exact then normalized.

    Returns (score, evidence).
    Exact match → 1.0
    Normalized match → 0.8
    No match → 0.0
    """
    evidence: dict = {
        "source_reference": source_ref,
        "target_reference": target_ref,
        "source_normalized": source_norm_ref,
        "target_normalized": target_norm_ref,
    }

    if source_ref and target_ref and source_ref == target_ref:
        evidence["method"] = "exact"
        return ONE, evidence

    if source_norm_ref and target_norm_ref and source_norm_ref == target_norm_ref:
        evidence["method"] = "normalized"
        return Decimal("0.8"), evidence

    evidence["method"] = "none"
    return ZERO, evidence


def match_amount(
    source_amount: Decimal,
    target_amount: Decimal,
    config: MatchConfig,
) -> tuple[Decimal, dict]:
    """
    Amount matching with tolerance.

    Exact → 1.0
    Within tolerance → 1.0
    Within upper tolerance → linear decay from 1.0 to 0.0
    Beyond upper tolerance → 0.0
    """
    diff = abs(source_amount - target_amount)

    evidence: dict = {
        "source_amount": str(source_amount),
        "target_amount": str(target_amount),
        "difference": str(diff),
        "tolerance": str(config.amount_tolerance),
        "tolerance_upper": str(config.amount_tolerance_upper),
    }

    if diff == ZERO:
        evidence["method"] = "exact"
        return ONE, evidence

    if diff <= config.amount_tolerance:
        evidence["method"] = "within_tolerance"
        return ONE, evidence

    if diff <= config.amount_tolerance_upper:
        # Linear decay between tolerance and upper tolerance
        range_size = config.amount_tolerance_upper - config.amount_tolerance
        if range_size > ZERO:
            excess = diff - config.amount_tolerance
            score = ONE - (excess / range_size)
            score = max(ZERO, min(ONE, score))
        else:
            score = ZERO
        evidence["method"] = "partial_tolerance"
        evidence["score_detail"] = str(score)
        return score, evidence

    evidence["method"] = "out_of_tolerance"
    return ZERO, evidence


def match_date(
    source_date: date,
    target_date: date,
    config: MatchConfig,
) -> tuple[Decimal, dict]:
    """
    Date matching with day tolerance.

    Exact → 1.0
    Within tolerance_days → 1.0
    Within upper tolerance → linear decay
    Beyond → 0.0
    """
    day_diff = abs((source_date - target_date).days)

    evidence: dict = {
        "source_date": source_date.isoformat(),
        "target_date": target_date.isoformat(),
        "day_difference": day_diff,
        "tolerance_days": config.date_tolerance_days,
        "tolerance_days_upper": config.date_tolerance_days_upper,
    }

    if day_diff == 0:
        evidence["method"] = "exact"
        return ONE, evidence

    if day_diff <= config.date_tolerance_days:
        evidence["method"] = "within_tolerance"
        return ONE, evidence

    if day_diff <= config.date_tolerance_days_upper:
        range_size = config.date_tolerance_days_upper - config.date_tolerance_days
        if range_size > 0:
            excess = day_diff - config.date_tolerance_days
            score = ONE - Decimal(str(excess)) / Decimal(str(range_size))
            score = max(ZERO, min(ONE, score))
        else:
            score = ZERO
        evidence["method"] = "partial_tolerance"
        return score, evidence

    evidence["method"] = "out_of_tolerance"
    return ZERO, evidence


def match_counterparty(
    source_counterparty: str,
    target_counterparty: str,
    source_norm_cp: str,
    target_norm_cp: str,
) -> tuple[Decimal, dict]:
    """
    Counterparty matching — exact, normalized-exact, then controlled similarity.

    Exact → 1.0
    Normalized exact → 0.9
    Similarity > 0.8 → bounded similarity score * 0.8 (capped)
    Below → 0.0

    Similarity is bounded and controlled — it never overrides deterministic rules.
    """
    evidence: dict = {
        "source_counterparty": source_counterparty,
        "target_counterparty": target_counterparty,
        "source_normalized": source_norm_cp,
        "target_normalized": target_norm_cp,
    }

    # Both empty → neutral (1.0 to avoid penalizing missing data)
    if not source_norm_cp and not target_norm_cp:
        evidence["method"] = "both_empty"
        return ONE, evidence

    # One empty → 0
    if not source_norm_cp or not target_norm_cp:
        evidence["method"] = "one_empty"
        return ZERO, evidence

    # Exact raw match
    if source_counterparty == target_counterparty:
        evidence["method"] = "exact"
        return ONE, evidence

    # Normalized exact match
    if source_norm_cp == target_norm_cp:
        evidence["method"] = "normalized"
        return Decimal("0.9"), evidence

    # Controlled similarity — SequenceMatcher is deterministic for same inputs
    ratio = SequenceMatcher(None, source_norm_cp, target_norm_cp).ratio()

    evidence["method"] = "similarity"
    evidence["similarity_ratio"] = f"{ratio:.4f}"

    # Only accept high similarity, and cap the resulting score
    if ratio >= 0.8:
        # Map [0.8, 1.0] → [0.5, 0.8] — controlled, bounded
        bounded_score = Decimal("0.5") + Decimal(str(ratio - 0.8)) * Decimal("1.5")
        bounded_score = min(bounded_score, Decimal("0.8"))
        return bounded_score, evidence

    return ZERO, evidence
