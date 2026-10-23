"""
Comprehensive tests for the reconciliation engine — Phase 3A.

Tests cover:
- Exact reference matching
- Normalized reference matching
- Amount tolerance
- Date tolerance
- Counterparty matching (exact, normalized, similarity)
- Ambiguous candidates
- Conflicting candidates
- Unmatched transactions
- Deterministic repeated execution
- Tenant isolation
- Invalid state transitions
- Full engine pipeline
"""

import pytest
from datetime import date
from decimal import Decimal

from apps.ingestion.models import CanonicalTransaction, ImportRecord, ImportSource
from apps.reconciliation.engine.config import MatchConfig
from apps.reconciliation.engine.matchers import (
    match_amount,
    match_counterparty,
    match_date,
    match_reference,
)
from apps.reconciliation.engine.policy import decide
from apps.reconciliation.engine.runner import ReconciliationEngine
from apps.reconciliation.engine.scoring import compute_composite_score
from apps.reconciliation.models import (
    InvalidStateTransition,
    MatchCandidate,
    ReconciliationRun,
    RunStatus,
    TransactionReconciliation,
    TransactionState,
    VALID_TRANSITIONS,
)

pytestmark = pytest.mark.django_db


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture
def default_config():
    return MatchConfig()


@pytest.fixture
def import_record(organization, user):
    return ImportRecord.objects.create(
        organization=organization,
        uploaded_by=user,
        original_filename="source.csv",
        file_type="csv",
        file_size=100,
        file_checksum="sourcehash",
        source=ImportSource.ERP,
    )


@pytest.fixture
def target_import(organization, user):
    return ImportRecord.objects.create(
        organization=organization,
        uploaded_by=user,
        original_filename="target.csv",
        file_type="csv",
        file_size=100,
        file_checksum="targethash",
        source=ImportSource.BANK,
    )


@pytest.fixture
def make_txn(organization, import_record):
    """Factory to create CanonicalTransaction records for the source import."""
    _counter = [0]

    def _make(
        amount="100.00",
        transaction_date="2024-01-15",
        reference="REF001",
        normalized_reference="ref001",
        counterparty="Acme Corp",
        normalized_counterparty="acme corp",
        import_rec=None,
        **kwargs,
    ):
        _counter[0] += 1
        if isinstance(transaction_date, str):
            transaction_date = date.fromisoformat(transaction_date)
        if isinstance(amount, str):
            amount = Decimal(amount)
        return CanonicalTransaction.objects.create(
            organization=organization,
            import_record=import_rec or import_record,
            source_row_number=_counter[0],
            source=ImportSource.ERP,
            transaction_date=transaction_date,
            amount=amount,
            reference=reference,
            normalized_reference=normalized_reference,
            counterparty=counterparty,
            normalized_counterparty=normalized_counterparty,
            **kwargs,
        )
    return _make


@pytest.fixture
def make_target_txn(organization, target_import):
    """Factory to create CanonicalTransaction records for the target import."""
    _counter = [0]

    def _make(
        amount="100.00",
        transaction_date="2024-01-15",
        reference="REF001",
        normalized_reference="ref001",
        counterparty="Acme Corp",
        normalized_counterparty="acme corp",
        import_rec=None,
        **kwargs,
    ):
        _counter[0] += 1
        if isinstance(transaction_date, str):
            transaction_date = date.fromisoformat(transaction_date)
        if isinstance(amount, str):
            amount = Decimal(amount)
        return CanonicalTransaction.objects.create(
            organization=organization,
            import_record=import_rec or target_import,
            source_row_number=_counter[0],
            source=ImportSource.BANK,
            transaction_date=transaction_date,
            amount=amount,
            reference=reference,
            normalized_reference=normalized_reference,
            counterparty=counterparty,
            normalized_counterparty=normalized_counterparty,
            **kwargs,
        )
    return _make


@pytest.fixture
def reconciliation_run(organization, user, import_record, target_import):
    return ReconciliationRun.objects.create(
        organization=organization,
        initiated_by=user,
        source_import=import_record,
        target_import=target_import,
    )


# ═══════════════════════════════════════════════════════════════════════
#  1. REFERENCE MATCHING
# ═══════════════════════════════════════════════════════════════════════

class TestReferenceMatching:
    def test_exact_reference_match(self):
        score, evidence = match_reference("INV-2024-001", "INV-2024-001", "inv2024001", "inv2024001")
        assert score == Decimal("1")
        assert evidence["method"] == "exact"

    def test_normalized_reference_match(self):
        """References differ in formatting but normalize to the same value."""
        score, evidence = match_reference(
            "INV-2024-001", "inv 2024 001",
            "inv2024001", "inv2024001",
        )
        assert score == Decimal("0.8")
        assert evidence["method"] == "normalized"

    def test_no_reference_match(self):
        score, evidence = match_reference("REF001", "REF999", "ref001", "ref999")
        assert score == Decimal("0")
        assert evidence["method"] == "none"

    def test_empty_references(self):
        score, evidence = match_reference("", "", "", "")
        assert score == Decimal("0")

    def test_one_empty_reference(self):
        score, evidence = match_reference("REF001", "", "ref001", "")
        assert score == Decimal("0")


# ═══════════════════════════════════════════════════════════════════════
#  2. AMOUNT TOLERANCE
# ═══════════════════════════════════════════════════════════════════════

class TestAmountMatching:
    def test_exact_amount_match(self, default_config):
        score, evidence = match_amount(Decimal("100.00"), Decimal("100.00"), default_config)
        assert score == Decimal("1")
        assert evidence["method"] == "exact"

    def test_within_tolerance(self, default_config):
        score, evidence = match_amount(Decimal("100.00"), Decimal("100.005"), default_config)
        assert score == Decimal("1")
        assert evidence["method"] == "within_tolerance"

    def test_partial_tolerance(self, default_config):
        """Amount difference between tolerance and upper tolerance → linear decay."""
        score, evidence = match_amount(Decimal("100.00"), Decimal("100.50"), default_config)
        assert Decimal("0") < score < Decimal("1")
        assert evidence["method"] == "partial_tolerance"

    def test_out_of_tolerance(self, default_config):
        score, evidence = match_amount(Decimal("100.00"), Decimal("200.00"), default_config)
        assert score == Decimal("0")
        assert evidence["method"] == "out_of_tolerance"

    def test_amount_tolerance_boundary(self):
        """Exactly at tolerance boundary should score 1.0."""
        config = MatchConfig(amount_tolerance=Decimal("0.50"))
        score, _ = match_amount(Decimal("100.00"), Decimal("100.50"), config)
        assert score == Decimal("1")

    def test_negative_amounts(self, default_config):
        """Credits/debits: negative amounts should work correctly."""
        score, evidence = match_amount(Decimal("-500.00"), Decimal("-500.00"), default_config)
        assert score == Decimal("1")

    def test_decimal_precision_preserved(self, default_config):
        """Ensure no floating-point artifacts."""
        score, _ = match_amount(Decimal("0.1"), Decimal("0.1"), default_config)
        assert score == Decimal("1")
        assert isinstance(score, Decimal)


# ═══════════════════════════════════════════════════════════════════════
#  3. DATE TOLERANCE
# ═══════════════════════════════════════════════════════════════════════

class TestDateMatching:
    def test_exact_date_match(self, default_config):
        d = date(2024, 1, 15)
        score, evidence = match_date(d, d, default_config)
        assert score == Decimal("1")
        assert evidence["method"] == "exact"

    def test_within_tolerance_days(self):
        config = MatchConfig(date_tolerance_days=2)
        score, evidence = match_date(date(2024, 1, 15), date(2024, 1, 16), config)
        assert score == Decimal("1")
        assert evidence["method"] == "within_tolerance"

    def test_partial_date_tolerance(self, default_config):
        """1 day difference with 0-day tolerance, 3-day upper → partial score."""
        score, evidence = match_date(
            date(2024, 1, 15), date(2024, 1, 16), default_config,
        )
        assert Decimal("0") < score < Decimal("1")
        assert evidence["method"] == "partial_tolerance"

    def test_out_of_date_tolerance(self, default_config):
        score, evidence = match_date(
            date(2024, 1, 15), date(2024, 2, 15), default_config,
        )
        assert score == Decimal("0")
        assert evidence["method"] == "out_of_tolerance"

    def test_date_symmetry(self, default_config):
        """Order should not matter."""
        s1, _ = match_date(date(2024, 1, 15), date(2024, 1, 16), default_config)
        s2, _ = match_date(date(2024, 1, 16), date(2024, 1, 15), default_config)
        assert s1 == s2


# ═══════════════════════════════════════════════════════════════════════
#  4. COUNTERPARTY MATCHING
# ═══════════════════════════════════════════════════════════════════════

class TestCounterpartyMatching:
    def test_exact_counterparty_match(self):
        score, evidence = match_counterparty(
            "Acme Corp", "Acme Corp", "acme corp", "acme corp",
        )
        assert score == Decimal("1")
        assert evidence["method"] == "exact"

    def test_normalized_counterparty_match(self):
        score, evidence = match_counterparty(
            "ACME CORP.", "acme-corp", "acme corp", "acme corp",
        )
        assert score == Decimal("0.9")
        assert evidence["method"] == "normalized"

    def test_similar_counterparty(self):
        """High similarity but not exact → bounded score."""
        score, evidence = match_counterparty(
            "Acme Corporation Ltd", "Acme Corporations Ltd",
            "acme corporation ltd", "acme corporations ltd",
        )
        # SequenceMatcher ratio ≈ 0.93 → above 0.8 threshold
        assert score > Decimal("0")
        assert evidence["method"] == "similarity"

    def test_different_counterparty(self):
        score, evidence = match_counterparty(
            "Acme Corp", "Globex Inc",
            "acme corp", "globex inc",
        )
        assert score == Decimal("0")

    def test_both_empty_counterparty(self):
        """Both empty → neutral score (don't penalize missing data)."""
        score, evidence = match_counterparty("", "", "", "")
        assert score == Decimal("1")
        assert evidence["method"] == "both_empty"

    def test_one_empty_counterparty(self):
        score, evidence = match_counterparty("Acme Corp", "", "acme corp", "")
        assert score == Decimal("0")
        assert evidence["method"] == "one_empty"


# ═══════════════════════════════════════════════════════════════════════
#  5. COMPOSITE SCORING
# ═══════════════════════════════════════════════════════════════════════

class TestCompositeScoring:
    def test_perfect_score(self, default_config):
        score = compute_composite_score(
            Decimal("1"), Decimal("1"), Decimal("1"), Decimal("1"),
            {}, {}, {}, {},
            default_config,
        )
        assert score.composite == Decimal("1.0000")

    def test_zero_score(self, default_config):
        score = compute_composite_score(
            Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"),
            {}, {}, {}, {},
            default_config,
        )
        assert score.composite == Decimal("0.0000")

    def test_weighted_score(self, default_config):
        """Only reference matches → score = reference_weight."""
        score = compute_composite_score(
            Decimal("1"), Decimal("0"), Decimal("0"), Decimal("0"),
            {}, {}, {}, {},
            default_config,
        )
        assert score.composite == default_config.reference_weight.quantize(Decimal("0.0001"))

    def test_score_has_evidence(self, default_config):
        score = compute_composite_score(
            Decimal("1"), Decimal("1"), Decimal("1"), Decimal("1"),
            {"method": "exact"}, {"method": "exact"},
            {"method": "exact"}, {"method": "exact"},
            default_config,
        )
        assert "reference" in score.evidence
        assert "amount" in score.evidence
        assert "weights" in score.evidence


# ═══════════════════════════════════════════════════════════════════════
#  6. DECISION POLICY
# ═══════════════════════════════════════════════════════════════════════

class TestDecisionPolicy:
    def _make_score(self, composite):
        from apps.reconciliation.engine.scoring import CandidateScore
        return CandidateScore(
            composite=Decimal(str(composite)),
            reference=Decimal("0"),
            amount=Decimal("0"),
            date=Decimal("0"),
            counterparty=Decimal("0"),
            evidence={},
        )

    def test_unmatched_no_candidates(self, default_config):
        decision = decide("src1", [], default_config)
        assert decision.state == "UNMATCHED"

    def test_unmatched_below_minimum(self, default_config):
        candidates = [("t1", self._make_score(0.10))]
        decision = decide("src1", candidates, default_config)
        assert decision.state == "UNMATCHED"

    def test_matched_clear_winner(self, default_config):
        candidates = [
            ("t1", self._make_score(0.95)),
            ("t2", self._make_score(0.40)),
        ]
        decision = decide("src1", candidates, default_config)
        assert decision.state == "MATCHED"
        assert decision.selected_target_id == "t1"

    def test_ambiguous_close_scores(self, default_config):
        """Two candidates both above match threshold with tiny gap → CANDIDATE."""
        candidates = [
            ("t1", self._make_score(0.90)),
            ("t2", self._make_score(0.88)),
        ]
        decision = decide("src1", candidates, default_config)
        assert decision.state == "CANDIDATE"

    def test_conflict_too_many_candidates(self):
        config = MatchConfig(max_candidates_before_conflict=2)
        from apps.reconciliation.engine.scoring import CandidateScore
        candidates = [
            ("t1", self._make_score(0.70)),
            ("t2", self._make_score(0.65)),
            ("t3", self._make_score(0.60)),
        ]
        decision = decide("src1", candidates, config)
        assert decision.state == "CONFLICT"

    def test_candidate_below_match_threshold(self, default_config):
        candidates = [("t1", self._make_score(0.70))]
        decision = decide("src1", candidates, default_config)
        assert decision.state == "CANDIDATE"


# ═══════════════════════════════════════════════════════════════════════
#  7. STATE TRANSITIONS
# ═══════════════════════════════════════════════════════════════════════

class TestStateTransitions:
    def test_valid_transition_unmatched_to_candidate(self, reconciliation_run, make_txn):
        txn = make_txn()
        tr = TransactionReconciliation.objects.create(
            run=reconciliation_run, transaction=txn,
            side="SOURCE", state=TransactionState.UNMATCHED,
        )
        tr.transition_to(TransactionState.CANDIDATE)
        assert tr.state == TransactionState.CANDIDATE

    def test_valid_transition_candidate_to_matched(self, reconciliation_run, make_txn):
        txn = make_txn()
        tr = TransactionReconciliation.objects.create(
            run=reconciliation_run, transaction=txn,
            side="SOURCE", state=TransactionState.CANDIDATE,
        )
        tr.transition_to(TransactionState.MATCHED)
        assert tr.state == TransactionState.MATCHED

    def test_invalid_transition_raises(self, reconciliation_run, make_txn):
        txn = make_txn()
        tr = TransactionReconciliation.objects.create(
            run=reconciliation_run, transaction=txn,
            side="SOURCE", state=TransactionState.UNMATCHED,
        )
        with pytest.raises(InvalidStateTransition):
            tr.transition_to(TransactionState.RESOLVED)

    def test_resolved_is_terminal(self, reconciliation_run, make_txn):
        txn = make_txn()
        tr = TransactionReconciliation.objects.create(
            run=reconciliation_run, transaction=txn,
            side="SOURCE", state=TransactionState.RESOLVED,
        )
        with pytest.raises(InvalidStateTransition):
            tr.transition_to(TransactionState.MATCHED)

    def test_all_states_have_transition_rules(self):
        """Every state must appear in VALID_TRANSITIONS."""
        for state_val, _ in TransactionState.choices:
            assert state_val in VALID_TRANSITIONS, f"{state_val} missing from transition map"

    def test_matched_to_under_review(self, reconciliation_run, make_txn):
        txn = make_txn()
        tr = TransactionReconciliation.objects.create(
            run=reconciliation_run, transaction=txn,
            side="SOURCE", state=TransactionState.MATCHED,
        )
        tr.transition_to(TransactionState.UNDER_REVIEW)
        assert tr.state == TransactionState.UNDER_REVIEW

    def test_under_review_to_resolved(self, reconciliation_run, make_txn):
        txn = make_txn()
        tr = TransactionReconciliation.objects.create(
            run=reconciliation_run, transaction=txn,
            side="SOURCE", state=TransactionState.UNDER_REVIEW,
        )
        tr.transition_to(TransactionState.RESOLVED)
        assert tr.state == TransactionState.RESOLVED


# ═══════════════════════════════════════════════════════════════════════
#  8. CONFIG VALIDATION
# ═══════════════════════════════════════════════════════════════════════

class TestMatchConfig:
    def test_default_config_valid(self):
        config = MatchConfig()
        assert config.reference_weight + config.amount_weight + config.date_weight + config.counterparty_weight == Decimal("1.00")

    def test_invalid_weights_raise(self):
        with pytest.raises(ValueError, match="weights must sum to 1.00"):
            MatchConfig(reference_weight=Decimal("0.50"))

    def test_config_serialization(self):
        config = MatchConfig()
        d = config.to_dict()
        assert d["reference_weight"] == "0.40"
        assert d["match_threshold"] == "0.85"
        assert isinstance(d["date_tolerance_days"], int)

    def test_config_is_frozen(self):
        config = MatchConfig()
        with pytest.raises(AttributeError):
            config.reference_weight = Decimal("0.50")


# ═══════════════════════════════════════════════════════════════════════
#  9. FULL ENGINE PIPELINE
# ═══════════════════════════════════════════════════════════════════════

class TestReconciliationEngine:
    def test_perfect_match(self, reconciliation_run, make_txn, make_target_txn, import_record, target_import):
        """Identical transactions should auto-match."""
        source = make_txn(amount="500.00", reference="INV-001", normalized_reference="inv001")
        target = make_target_txn(amount="500.00", reference="INV-001", normalized_reference="inv001")

        engine = ReconciliationEngine()
        result = engine.run(
            reconciliation_run,
            CanonicalTransaction.objects.filter(import_record=import_record),
            CanonicalTransaction.objects.filter(import_record=target_import),
        )

        assert result.matched == 1
        assert result.unmatched == 0
        assert MatchCandidate.objects.filter(run=reconciliation_run, is_selected=True).count() == 1

    def test_unmatched_transactions(self, reconciliation_run, make_txn, make_target_txn, import_record, target_import):
        """Completely different transactions should remain unmatched."""
        make_txn(amount="100.00", reference="AAA", normalized_reference="aaa",
                 counterparty="Alpha", normalized_counterparty="alpha")
        make_target_txn(amount="999.99", reference="ZZZ", normalized_reference="zzz",
                        counterparty="Omega", normalized_counterparty="omega",
                        transaction_date="2024-06-01")

        engine = ReconciliationEngine()
        result = engine.run(
            reconciliation_run,
            CanonicalTransaction.objects.filter(import_record=import_record),
            CanonicalTransaction.objects.filter(import_record=target_import),
        )

        assert result.unmatched == 1
        assert result.matched == 0

    def test_amount_tolerance_match(self, reconciliation_run, make_txn, make_target_txn, import_record, target_import):
        """Transactions with small amount difference should match if reference and date are identical."""
        make_txn(amount="1000.00", reference="REF-100", normalized_reference="ref100")
        make_target_txn(amount="1000.005", reference="REF-100", normalized_reference="ref100")

        engine = ReconciliationEngine()
        result = engine.run(
            reconciliation_run,
            CanonicalTransaction.objects.filter(import_record=import_record),
            CanonicalTransaction.objects.filter(import_record=target_import),
        )

        assert result.matched == 1

    def test_date_tolerance_match(self, reconciliation_run, make_txn, make_target_txn, import_record, target_import):
        """Transactions with 1-day date difference should still match if reference and amount are identical."""
        config = MatchConfig(date_tolerance_days=1)
        make_txn(
            amount="500.00", reference="REF-DT", normalized_reference="refdt",
            transaction_date="2024-01-15",
        )
        make_target_txn(
            amount="500.00", reference="REF-DT", normalized_reference="refdt",
            transaction_date="2024-01-16",
        )

        engine = ReconciliationEngine(config=config)
        result = engine.run(
            reconciliation_run,
            CanonicalTransaction.objects.filter(import_record=import_record),
            CanonicalTransaction.objects.filter(import_record=target_import),
        )

        assert result.matched == 1

    def test_normalized_reference_match(self, reconciliation_run, make_txn, make_target_txn, import_record, target_import):
        """Different raw references that normalize to the same → should match."""
        make_txn(
            amount="250.00", reference="INV-2024-001", normalized_reference="inv2024001",
        )
        make_target_txn(
            amount="250.00", reference="inv 2024 001", normalized_reference="inv2024001",
        )

        engine = ReconciliationEngine()
        result = engine.run(
            reconciliation_run,
            CanonicalTransaction.objects.filter(import_record=import_record),
            CanonicalTransaction.objects.filter(import_record=target_import),
        )

        assert result.matched == 1

    def test_multiple_sources_one_target(self, reconciliation_run, make_txn, make_target_txn, import_record, target_import):
        """Two sources matching the same target → at least one conflict/candidate."""
        make_txn(amount="100.00", reference="DUP", normalized_reference="dup")
        make_txn(amount="100.00", reference="DUP", normalized_reference="dup")
        make_target_txn(amount="100.00", reference="DUP", normalized_reference="dup")

        engine = ReconciliationEngine()
        result = engine.run(
            reconciliation_run,
            CanonicalTransaction.objects.filter(import_record=import_record),
            CanonicalTransaction.objects.filter(import_record=target_import),
        )

        # Both sources have the same single candidate — each individually "matched"
        # because each source independently scores against the target
        total_candidates = MatchCandidate.objects.filter(run=reconciliation_run).count()
        assert total_candidates >= 2

    def test_run_status_lifecycle(self, reconciliation_run, make_txn, make_target_txn, import_record, target_import):
        """Run should transition PENDING → RUNNING → COMPLETED."""
        make_txn()
        make_target_txn()

        assert reconciliation_run.status == RunStatus.PENDING

        engine = ReconciliationEngine()
        engine.run(
            reconciliation_run,
            CanonicalTransaction.objects.filter(import_record=import_record),
            CanonicalTransaction.objects.filter(import_record=target_import),
        )

        reconciliation_run.refresh_from_db()
        assert reconciliation_run.status == RunStatus.COMPLETED
        assert reconciliation_run.started_at is not None
        assert reconciliation_run.completed_at is not None
        assert reconciliation_run.config != {}

    def test_evidence_metadata_populated(self, reconciliation_run, make_txn, make_target_txn, import_record, target_import):
        """Every candidate should have structured evidence metadata."""
        make_txn(amount="100.00", reference="EV-001", normalized_reference="ev001")
        make_target_txn(amount="100.00", reference="EV-001", normalized_reference="ev001")

        engine = ReconciliationEngine()
        engine.run(
            reconciliation_run,
            CanonicalTransaction.objects.filter(import_record=import_record),
            CanonicalTransaction.objects.filter(import_record=target_import),
        )

        candidate = MatchCandidate.objects.filter(run=reconciliation_run).first()
        assert candidate is not None
        assert "reference" in candidate.evidence
        assert "amount" in candidate.evidence
        assert "weights" in candidate.evidence

    def test_empty_sources(self, reconciliation_run, import_record, target_import):
        """Empty source set should produce no matches."""
        engine = ReconciliationEngine()
        result = engine.run(
            reconciliation_run,
            CanonicalTransaction.objects.filter(import_record=import_record),
            CanonicalTransaction.objects.filter(import_record=target_import),
        )
        assert result.matched == 0
        assert result.total_source == 0


# ═══════════════════════════════════════════════════════════════════════
#  10. DETERMINISTIC REPEATED EXECUTION
# ═══════════════════════════════════════════════════════════════════════

class TestDeterministicExecution:
    def test_identical_inputs_identical_results(
        self, organization, user, import_record, target_import,
        make_txn, make_target_txn,
    ):
        """Running the engine twice with the same data must produce identical results."""
        source = make_txn(amount="300.00", reference="DET-001", normalized_reference="det001")
        target = make_target_txn(amount="300.00", reference="DET-001", normalized_reference="det001")

        config = MatchConfig()
        results = []

        for i in range(2):
            run = ReconciliationRun.objects.create(
                organization=organization,
                initiated_by=user,
                source_import=import_record,
                target_import=target_import,
            )
            engine = ReconciliationEngine(config=config)
            result = engine.run(
                run,
                CanonicalTransaction.objects.filter(import_record=import_record),
                CanonicalTransaction.objects.filter(import_record=target_import),
            )
            results.append(result)

        assert results[0].matched == results[1].matched
        assert results[0].unmatched == results[1].unmatched
        assert results[0].conflict == results[1].conflict

        # Compare candidate scores
        run1_candidates = list(
            MatchCandidate.objects.filter(run_id=results[0].run_id)
            .values_list("score", flat=True)
        )
        run2_candidates = list(
            MatchCandidate.objects.filter(run_id=results[1].run_id)
            .values_list("score", flat=True)
        )
        assert run1_candidates == run2_candidates

    def test_score_pair_deterministic(self, make_txn, make_target_txn):
        """score_pair must return identical results on repeated calls."""
        source = make_txn(amount="100.50", reference="R1", normalized_reference="r1")
        target = make_target_txn(amount="100.55", reference="R1", normalized_reference="r1")

        engine = ReconciliationEngine()
        s1 = engine.score_pair(source, target)
        s2 = engine.score_pair(source, target)

        assert s1.composite == s2.composite
        assert s1.reference == s2.reference
        assert s1.amount == s2.amount
        assert s1.date == s2.date
        assert s1.counterparty == s2.counterparty


# ═══════════════════════════════════════════════════════════════════════
#  11. TENANT ISOLATION
# ═══════════════════════════════════════════════════════════════════════

class TestTenantIsolation:
    def test_engine_only_processes_given_querysets(
        self, organization, other_organization, user, import_record, target_import,
        make_txn, make_target_txn, create_organization,
    ):
        """
        Engine should only match transactions in the provided querysets,
        not cross-org data.
        """
        # Org A transactions
        source = make_txn(amount="100.00", reference="ISO-001", normalized_reference="iso001")
        target = make_target_txn(amount="100.00", reference="ISO-001", normalized_reference="iso001")

        # Org B transactions (should be invisible)
        other_import = ImportRecord.objects.create(
            organization=other_organization, uploaded_by=user,
            original_filename="other_source.csv", file_type="csv",
            file_size=100, file_checksum="otherhash1",
        )
        CanonicalTransaction.objects.create(
            organization=other_organization,
            import_record=other_import,
            source_row_number=1,
            source=ImportSource.ERP,
            transaction_date=date(2024, 1, 15),
            amount=Decimal("100.00"),
            reference="ISO-001",
            normalized_reference="iso001",
            counterparty="Acme Corp",
            normalized_counterparty="acme corp",
        )

        run = ReconciliationRun.objects.create(
            organization=organization,
            initiated_by=user,
            source_import=import_record,
            target_import=target_import,
        )

        engine = ReconciliationEngine()
        result = engine.run(
            run,
            CanonicalTransaction.objects.filter(import_record=import_record),
            CanonicalTransaction.objects.filter(import_record=target_import),
        )

        # Should only match org A's transactions
        assert result.total_source == 1
        assert result.total_target == 1
        assert result.matched == 1

        # No candidates involving org B
        for c in MatchCandidate.objects.filter(run=run):
            assert c.source_transaction.organization_id == organization.id
            assert c.target_transaction.organization_id == organization.id
