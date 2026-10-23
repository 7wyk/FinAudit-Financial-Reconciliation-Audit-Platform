"""
Decision policy — classify candidates and assign reconciliation states.

Separated from scoring so that classification thresholds can be tuned
independently from how scores are computed.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from .config import MatchConfig
from .scoring import CandidateScore


@dataclass
class CandidateDecision:
    """Result of the decision policy for one source transaction's candidates."""

    source_id: object  # UUID or any hashable
    selected_target_id: object | None = None  # Target to match
    state: str = "UNMATCHED"
    candidates: list = field(default_factory=list)  # [(target_id, CandidateScore)]
    reason: str = ""


def decide(
    source_id: object,
    scored_candidates: list[tuple[object, CandidateScore]],
    config: MatchConfig,
) -> CandidateDecision:
    """
    Apply decision policy to a source transaction's scored candidates.

    Policy:
    1. Filter out candidates below minimum_candidate_score.
    2. Sort by composite score descending (deterministic: by score, then by target_id).
    3. If best candidate >= match_threshold and clearly dominant → MATCHED.
    4. If multiple candidates >= ambiguity_threshold → CONFLICT if > max, else CANDIDATE.
    5. If no candidates survive filtering → UNMATCHED.

    Returns a CandidateDecision with the chosen state and evidence.
    """
    # 1. Filter
    viable = [
        (tid, cs) for tid, cs in scored_candidates
        if cs.composite >= config.minimum_candidate_score
    ]

    if not viable:
        return CandidateDecision(
            source_id=source_id,
            state="UNMATCHED",
            reason="No candidates above minimum score threshold.",
        )

    # 2. Sort deterministically: by score descending, then by str(target_id) ascending
    viable.sort(key=lambda x: (-x[1].composite, str(x[0])))

    best_id, best_score = viable[0]

    # Count how many are above ambiguity threshold
    ambiguous = [
        (tid, cs) for tid, cs in viable
        if cs.composite >= config.ambiguity_threshold
    ]

    # 3. Single clear winner above match threshold
    if best_score.composite >= config.match_threshold:
        # Check if there's a close second (within 0.05 of best)
        if len(ambiguous) > 1:
            second_score = ambiguous[1][1].composite
            gap = best_score.composite - second_score
            if gap < Decimal("0.05"):
                # Too close — ambiguous/conflict
                if len(ambiguous) > config.max_candidates_before_conflict:
                    return CandidateDecision(
                        source_id=source_id,
                        state="CONFLICT",
                        candidates=viable,
                        reason=(
                            f"{len(ambiguous)} candidates above ambiguity threshold "
                            f"with insufficient separation (gap={gap})."
                        ),
                    )
                return CandidateDecision(
                    source_id=source_id,
                    state="CANDIDATE",
                    candidates=viable,
                    reason=(
                        f"Top candidates too close (gap={gap}). "
                        f"Requires human review."
                    ),
                )

        # Clear winner
        return CandidateDecision(
            source_id=source_id,
            selected_target_id=best_id,
            state="MATCHED",
            candidates=viable,
            reason=f"Clear match with score {best_score.composite}.",
        )

    # 4. Candidates exist but none meet match threshold
    if len(ambiguous) > config.max_candidates_before_conflict:
        return CandidateDecision(
            source_id=source_id,
            state="CONFLICT",
            candidates=viable,
            reason=(
                f"{len(ambiguous)} candidates above ambiguity threshold "
                f"exceed conflict limit ({config.max_candidates_before_conflict})."
            ),
        )

    if ambiguous:
        return CandidateDecision(
            source_id=source_id,
            state="CANDIDATE",
            candidates=viable,
            reason=(
                f"{len(ambiguous)} candidate(s) above ambiguity threshold "
                f"but below match threshold."
            ),
        )

    # 5. Below ambiguity threshold — keep as weak candidates if above minimum
    return CandidateDecision(
        source_id=source_id,
        state="CANDIDATE",
        candidates=viable,
        reason="Candidates exist but below ambiguity threshold.",
    )
