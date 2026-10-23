"""
Reconciliation models — runs, match candidates, and transaction reconciliation state.

All models are org-scoped. The reconciliation engine writes to these models
but the matching logic itself lives in the engine/ subpackage.
"""

from django.conf import settings
from django.db import models

from apps.common.models import BaseModel


# ── Reconciliation states ────────────────────────────────────────────

class TransactionState(models.TextChoices):
    """State of a single transaction with respect to reconciliation."""
    UNMATCHED = "UNMATCHED", "Unmatched"
    CANDIDATE = "CANDIDATE", "Has candidates"
    MATCHED = "MATCHED", "Matched"
    PARTIALLY_MATCHED = "PARTIALLY_MATCHED", "Partially matched"
    CONFLICT = "CONFLICT", "Conflicting candidates"
    EXCEPTION = "EXCEPTION", "Exception"
    UNDER_REVIEW = "UNDER_REVIEW", "Under review"
    RESOLVED = "RESOLVED", "Resolved"
    REJECTED = "REJECTED", "Rejected"


# Valid state transitions — anything not listed here is forbidden
VALID_TRANSITIONS: dict[str, set[str]] = {
    TransactionState.UNMATCHED: {
        TransactionState.CANDIDATE,
        TransactionState.MATCHED,
        TransactionState.EXCEPTION,
    },
    TransactionState.CANDIDATE: {
        TransactionState.MATCHED,
        TransactionState.CONFLICT,
        TransactionState.UNMATCHED,
        TransactionState.EXCEPTION,
        TransactionState.UNDER_REVIEW,
    },
    TransactionState.MATCHED: {
        TransactionState.EXCEPTION,
        TransactionState.UNDER_REVIEW,
    },
    TransactionState.PARTIALLY_MATCHED: {
        TransactionState.MATCHED,
        TransactionState.EXCEPTION,
        TransactionState.UNDER_REVIEW,
    },
    TransactionState.CONFLICT: {
        TransactionState.UNDER_REVIEW,
        TransactionState.EXCEPTION,
        TransactionState.CANDIDATE,
    },
    TransactionState.EXCEPTION: {
        TransactionState.UNDER_REVIEW,
    },
    TransactionState.UNDER_REVIEW: {
        TransactionState.RESOLVED,
        TransactionState.REJECTED,
        TransactionState.MATCHED,
        TransactionState.EXCEPTION,
    },
    TransactionState.RESOLVED: set(),  # Terminal
    TransactionState.REJECTED: {
        TransactionState.UNDER_REVIEW,
    },
}


class InvalidStateTransition(Exception):
    """Raised when a state transition is not permitted."""

    def __init__(self, from_state: str, to_state: str):
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"Invalid state transition: {from_state} → {to_state}"
        )


# ── Run status ───────────────────────────────────────────────────────

class RunStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    RUNNING = "RUNNING", "Running"
    COMPLETED = "COMPLETED", "Completed"
    FAILED = "FAILED", "Failed"


class CandidateReviewStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    CONFIRMED = "CONFIRMED", "Confirmed"
    REJECTED = "REJECTED", "Rejected"


# ── Models ───────────────────────────────────────────────────────────

class ReconciliationRun(BaseModel):
    """
    A single reconciliation execution comparing two sets of transactions.

    Stores configuration parameters used for the run so that results are
    reproducible and auditable.
    """

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="reconciliation_runs",
    )
    initiated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="reconciliation_runs",
    )

    # Which imports are being reconciled
    source_import = models.ForeignKey(
        "ingestion.ImportRecord",
        on_delete=models.CASCADE,
        related_name="source_runs",
    )
    target_import = models.ForeignKey(
        "ingestion.ImportRecord",
        on_delete=models.CASCADE,
        related_name="target_runs",
    )

    status = models.CharField(
        max_length=20, choices=RunStatus.choices, default=RunStatus.PENDING,
    )

    # Configuration — persisted for reproducibility
    config = models.JSONField(
        default=dict,
        help_text="Matching parameters used for this run",
    )

    # Summary statistics
    total_source = models.PositiveIntegerField(default=0)
    total_target = models.PositiveIntegerField(default=0)
    matched_count = models.PositiveIntegerField(default=0)
    unmatched_count = models.PositiveIntegerField(default=0)
    conflict_count = models.PositiveIntegerField(default=0)
    exception_count = models.PositiveIntegerField(default=0)

    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, default="")

    class Meta:
        db_table = "reconciliation_runs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Run {self.id} ({self.status})"


class TransactionReconciliation(BaseModel):
    """
    Tracks the reconciliation state of a single CanonicalTransaction
    within a specific run.
    """

    run = models.ForeignKey(
        ReconciliationRun,
        on_delete=models.CASCADE,
        related_name="transaction_states",
    )
    transaction = models.ForeignKey(
        "ingestion.CanonicalTransaction",
        on_delete=models.CASCADE,
        related_name="reconciliation_states",
    )
    side = models.CharField(
        max_length=10,
        choices=[("SOURCE", "Source"), ("TARGET", "Target")],
    )
    state = models.CharField(
        max_length=25,
        choices=TransactionState.choices,
        default=TransactionState.UNMATCHED,
    )

    class Meta:
        db_table = "transaction_reconciliations"
        constraints = [
            models.UniqueConstraint(
                fields=("run", "transaction"),
                name="unique_run_transaction",
            ),
        ]

    def __str__(self):
        return f"Txn {self.transaction_id} [{self.state}]"

    def transition_to(self, new_state: str) -> None:
        """
        Enforce valid state transitions. Raises InvalidStateTransition
        if the transition is not permitted.
        """
        if not self.can_transition_to(new_state):
            raise InvalidStateTransition(self.state, new_state)
        self.state = new_state

    def can_transition_to(self, new_state: str) -> bool:
        """Return whether a requested workflow state change is valid."""
        return new_state in VALID_TRANSITIONS.get(self.state, set())


class ReconciliationInvestigationNote(BaseModel):
    """Human-authored context captured during reconciliation review."""

    transaction_reconciliation = models.ForeignKey(
        TransactionReconciliation,
        on_delete=models.CASCADE,
        related_name="investigation_notes",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="reconciliation_investigation_notes",
    )
    content = models.TextField()

    class Meta:
        db_table = "reconciliation_investigation_notes"
        ordering = ["created_at"]

    def __str__(self):
        return f"Note for {self.transaction_reconciliation_id}"


class MatchCandidate(BaseModel):
    """
    A candidate match between a source and target transaction produced by
    the reconciliation engine.

    Contains deterministic score, component breakdowns, and evidence metadata.
    """

    run = models.ForeignKey(
        ReconciliationRun,
        on_delete=models.CASCADE,
        related_name="candidates",
    )
    source_transaction = models.ForeignKey(
        "ingestion.CanonicalTransaction",
        on_delete=models.CASCADE,
        related_name="source_candidates",
    )
    target_transaction = models.ForeignKey(
        "ingestion.CanonicalTransaction",
        on_delete=models.CASCADE,
        related_name="target_candidates",
    )

    # Deterministic composite score [0.0, 1.0]
    score = models.DecimalField(max_digits=5, decimal_places=4)

    # Component scores for explanation
    reference_score = models.DecimalField(max_digits=5, decimal_places=4, default=0)
    amount_score = models.DecimalField(max_digits=5, decimal_places=4, default=0)
    date_score = models.DecimalField(max_digits=5, decimal_places=4, default=0)
    counterparty_score = models.DecimalField(max_digits=5, decimal_places=4, default=0)

    # Evidence — human-readable explanation of why this candidate was generated
    evidence = models.JSONField(
        default=dict,
        help_text="Structured explanation metadata",
    )

    # Whether the engine selected this candidate as the match
    is_selected = models.BooleanField(default=False)
    review_status = models.CharField(
        max_length=20,
        choices=CandidateReviewStatus.choices,
        default=CandidateReviewStatus.PENDING,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_match_candidates",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "match_candidates"
        ordering = ["-score"]
        constraints = [
            models.UniqueConstraint(
                fields=("run", "source_transaction", "target_transaction"),
                name="unique_candidate_pair",
            ),
        ]

    def __str__(self):
        return (
            f"Candidate: {self.source_transaction_id} ↔ "
            f"{self.target_transaction_id} ({self.score})"
        )
