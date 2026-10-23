"""
ReconciliationEngine — orchestrates the full matching pipeline.

This is the main entry point. It:
1. Takes source and target CanonicalTransaction querysets
2. Generates candidates by scoring every source-target pair
3. Applies decision policy
4. Persists results to ReconciliationRun / MatchCandidate / TransactionReconciliation

The engine is independent of HTTP views. It can be called directly from
tests, management commands, or Celery tasks.
"""

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from django.utils import timezone

from .config import MatchConfig
from .matchers import match_amount, match_counterparty, match_date, match_reference
from .policy import CandidateDecision, decide
from .scoring import CandidateScore, compute_composite_score

logger = logging.getLogger(__name__)


@dataclass
class EngineResult:
    """Summary of a completed reconciliation run."""

    run_id: Any = None
    total_source: int = 0
    total_target: int = 0
    matched: int = 0
    unmatched: int = 0
    candidate: int = 0
    conflict: int = 0
    decisions: list[CandidateDecision] = field(default_factory=list)


class ReconciliationEngine:
    """
    Deterministic reconciliation engine.

    Usage:
        engine = ReconciliationEngine(config=MatchConfig())
        result = engine.run(run, source_qs, target_qs)
    """

    def __init__(self, config: MatchConfig | None = None):
        self.config = config or MatchConfig()

    def score_pair(self, source, target) -> CandidateScore:
        """
        Score a single source-target pair.

        Accepts any objects with the canonical transaction fields:
        reference, normalized_reference, amount, transaction_date,
        counterparty, normalized_counterparty.

        Returns a CandidateScore with component scores and evidence.
        """
        ref_score, ref_evidence = match_reference(
            source.reference, target.reference,
            source.normalized_reference, target.normalized_reference,
        )
        amt_score, amt_evidence = match_amount(
            source.amount, target.amount, self.config,
        )
        date_score, date_evidence = match_date(
            source.transaction_date, target.transaction_date, self.config,
        )
        cp_score, cp_evidence = match_counterparty(
            source.counterparty, target.counterparty,
            source.normalized_counterparty, target.normalized_counterparty,
        )

        return compute_composite_score(
            ref_score, amt_score, date_score, cp_score,
            ref_evidence, amt_evidence, date_evidence, cp_evidence,
            self.config,
        )

    def generate_candidates(
        self, source_txns, target_txns,
    ) -> dict[Any, list[tuple[Any, CandidateScore]]]:
        """
        Generate scored candidates for all source transactions.

        Returns: {source_id: [(target_id, CandidateScore), ...]}
        Sorted by score descending per source.
        """
        candidates: dict[Any, list[tuple[Any, CandidateScore]]] = {}

        for source in source_txns:
            src_candidates = []
            for target in target_txns:
                score = self.score_pair(source, target)
                if score.composite >= self.config.minimum_candidate_score:
                    src_candidates.append((target.id, score))

            # Deterministic sort: score desc, target_id asc
            src_candidates.sort(key=lambda x: (-x[1].composite, str(x[0])))
            candidates[source.id] = src_candidates

        return candidates

    def apply_decisions(
        self,
        candidates: dict[Any, list[tuple[Any, CandidateScore]]],
    ) -> list[CandidateDecision]:
        """
        Apply decision policy to all source transactions' candidates.

        Returns a list of CandidateDecision objects.
        """
        decisions = []
        for source_id, scored in candidates.items():
            decision = decide(source_id, scored, self.config)
            decisions.append(decision)
        return decisions

    def run(self, run_model, source_qs, target_qs) -> EngineResult:
        """
        Execute the full reconciliation pipeline and persist results.

        Args:
            run_model: ReconciliationRun instance
            source_qs: Queryset of source CanonicalTransactions
            target_qs: Queryset of target CanonicalTransactions

        Returns: EngineResult with summary statistics.
        """
        from apps.reconciliation.models import (
            MatchCandidate,
            RunStatus,
            TransactionReconciliation,
            TransactionState,
        )

        run_model.status = RunStatus.RUNNING
        run_model.started_at = timezone.now()
        run_model.config = self.config.to_dict()
        run_model.save(update_fields=["status", "started_at", "config"])

        try:
            source_list = list(source_qs)
            target_list = list(target_qs)

            result = EngineResult(
                run_id=run_model.id,
                total_source=len(source_list),
                total_target=len(target_list),
            )

            # 1. Generate candidates
            candidates = self.generate_candidates(source_list, target_list)

            # 2. Apply decision policy
            decisions = self.apply_decisions(candidates)
            result.decisions = decisions

            # 3. Persist results
            matched_target_ids = set()

            for decision in decisions:
                # Create TransactionReconciliation for source
                state_value = getattr(
                    TransactionState, decision.state, TransactionState.UNMATCHED
                )
                TransactionReconciliation.objects.create(
                    run=run_model,
                    transaction_id=decision.source_id,
                    side="SOURCE",
                    state=state_value,
                )

                # Persist all candidates
                for target_id, candidate_score in decision.candidates:
                    is_selected = (
                        decision.state == "MATCHED"
                        and target_id == decision.selected_target_id
                    )
                    MatchCandidate.objects.create(
                        run=run_model,
                        source_transaction_id=decision.source_id,
                        target_transaction_id=target_id,
                        score=candidate_score.composite,
                        reference_score=candidate_score.reference,
                        amount_score=candidate_score.amount,
                        date_score=candidate_score.date,
                        counterparty_score=candidate_score.counterparty,
                        evidence=candidate_score.evidence,
                        is_selected=is_selected,
                    )

                    if is_selected:
                        matched_target_ids.add(target_id)

                # Count states
                if decision.state == "MATCHED":
                    result.matched += 1
                elif decision.state == "CONFLICT":
                    result.conflict += 1
                elif decision.state == "UNMATCHED":
                    result.unmatched += 1
                else:
                    result.candidate += 1

            # 4. Create TransactionReconciliation for target transactions
            for target in target_list:
                if target.id in matched_target_ids:
                    state = TransactionState.MATCHED
                else:
                    state = TransactionState.UNMATCHED
                TransactionReconciliation.objects.create(
                    run=run_model,
                    transaction_id=target.id,
                    side="TARGET",
                    state=state,
                )

            # 5. Update run summary
            run_model.status = RunStatus.COMPLETED
            run_model.completed_at = timezone.now()
            run_model.total_source = result.total_source
            run_model.total_target = result.total_target
            run_model.matched_count = result.matched
            run_model.unmatched_count = result.unmatched
            run_model.conflict_count = result.conflict
            run_model.exception_count = 0
            run_model.save()

            logger.info(
                "Reconciliation run %s completed: %d matched, %d unmatched, "
                "%d candidates, %d conflicts",
                run_model.id, result.matched, result.unmatched,
                result.candidate, result.conflict,
            )

            return result

        except Exception as exc:
            run_model.status = RunStatus.FAILED
            run_model.completed_at = timezone.now()
            run_model.error_message = str(exc)[:2000]
            run_model.save(
                update_fields=["status", "completed_at", "error_message"]
            )
            raise
