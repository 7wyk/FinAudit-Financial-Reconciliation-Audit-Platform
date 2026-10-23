"""Application services for reconciliation execution and human review."""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.ingestion.models import CanonicalTransaction, ImportRecord

from .engine import ReconciliationEngine
from .models import (
    CandidateReviewStatus,
    MatchCandidate,
    ReconciliationInvestigationNote,
    ReconciliationRun,
    TransactionReconciliation,
    TransactionState,
)


def create_and_start_run(*, organization, initiated_by, source_import, target_import):
    """Create a tenant-scoped run and execute the existing deterministic engine."""
    if source_import.organization_id != organization.id:
        raise ValidationError("Source import does not belong to this organization.")
    if target_import.organization_id != organization.id:
        raise ValidationError("Target import does not belong to this organization.")
    if source_import.id == target_import.id:
        raise ValidationError("Source and target imports must be different.")

    run = ReconciliationRun.objects.create(
        organization=organization,
        initiated_by=initiated_by,
        source_import=source_import,
        target_import=target_import,
    )
    ReconciliationEngine().run(
        run,
        CanonicalTransaction.objects.filter(
            organization=organization, import_record=source_import
        ),
        CanonicalTransaction.objects.filter(
            organization=organization, import_record=target_import
        ),
    )
    run.refresh_from_db()
    return run


def _create_note(transaction_reconciliation, author, content):
    if content:
        ReconciliationInvestigationNote.objects.create(
            transaction_reconciliation=transaction_reconciliation,
            author=author,
            content=content,
        )


def confirm_candidate(*, transaction_reconciliation, candidate, user, note=""):
    """Confirm one candidate match using the domain state machine."""
    if candidate.run_id != transaction_reconciliation.run_id:
        raise ValidationError("Candidate does not belong to this reconciliation run.")
    if candidate.source_transaction_id != transaction_reconciliation.transaction_id:
        raise ValidationError("Candidate does not belong to this source transaction.")
    already_matched = transaction_reconciliation.state == TransactionState.MATCHED
    if not already_matched and not transaction_reconciliation.can_transition_to(TransactionState.MATCHED):
        raise ValidationError("This transaction cannot be confirmed from its current state.")
    if already_matched and not candidate.is_selected:
        raise ValidationError("Only the deterministic selected candidate can be confirmed.")

    with transaction.atomic():
        target_state = TransactionReconciliation.objects.select_for_update().get(
            run=transaction_reconciliation.run,
            transaction_id=candidate.target_transaction_id,
        )
        if target_state.state == TransactionState.MATCHED:
            selected_elsewhere = MatchCandidate.objects.filter(
                run=candidate.run,
                target_transaction_id=candidate.target_transaction_id,
                is_selected=True,
            ).exclude(pk=candidate.pk).exists()
            if selected_elsewhere:
                raise ValidationError("Target transaction is already confirmed elsewhere.")
        elif not target_state.can_transition_to(TransactionState.MATCHED):
            raise ValidationError("Target transaction cannot be confirmed from its current state.")

        MatchCandidate.objects.filter(
            run=candidate.run,
            source_transaction_id=candidate.source_transaction_id,
        ).update(is_selected=False)
        candidate.is_selected = True
        candidate.review_status = CandidateReviewStatus.CONFIRMED
        candidate.reviewed_by = user
        candidate.reviewed_at = timezone.now()
        candidate.save(update_fields=["is_selected", "review_status", "reviewed_by", "reviewed_at"])

        if not already_matched:
            transaction_reconciliation.transition_to(TransactionState.MATCHED)
            transaction_reconciliation.save(update_fields=["state", "updated_at"])
        if target_state.state != TransactionState.MATCHED:
            target_state.transition_to(TransactionState.MATCHED)
            target_state.save(update_fields=["state", "updated_at"])
        _create_note(transaction_reconciliation, user, note)
    return transaction_reconciliation


def reject_candidate(*, transaction_reconciliation, candidate, user, note=""):
    """Record a rejected candidate without reimplementing match selection."""
    if candidate.run_id != transaction_reconciliation.run_id:
        raise ValidationError("Candidate does not belong to this reconciliation run.")
    if candidate.source_transaction_id != transaction_reconciliation.transaction_id:
        raise ValidationError("Candidate does not belong to this source transaction.")
    if candidate.review_status == CandidateReviewStatus.CONFIRMED:
        raise ValidationError("A confirmed candidate cannot be rejected.")

    with transaction.atomic():
        candidate.is_selected = False
        candidate.review_status = CandidateReviewStatus.REJECTED
        candidate.reviewed_by = user
        candidate.reviewed_at = timezone.now()
        candidate.save(update_fields=["is_selected", "review_status", "reviewed_by", "reviewed_at"])

        remaining = MatchCandidate.objects.filter(
            run=candidate.run,
            source_transaction_id=candidate.source_transaction_id,
        ).exclude(review_status=CandidateReviewStatus.REJECTED).exists()
        if (
            not remaining
            and transaction_reconciliation.can_transition_to(TransactionState.UNMATCHED)
        ):
            transaction_reconciliation.transition_to(TransactionState.UNMATCHED)
            transaction_reconciliation.save(update_fields=["state", "updated_at"])
        _create_note(transaction_reconciliation, user, note)
    return transaction_reconciliation


def mark_exception(*, transaction_reconciliation, user, note=""):
    """Move a reviewable transaction into the exception workflow."""
    if not transaction_reconciliation.can_transition_to(TransactionState.EXCEPTION):
        raise ValidationError("This transaction cannot be marked as an exception.")
    transaction_reconciliation.transition_to(TransactionState.EXCEPTION)
    transaction_reconciliation.save(update_fields=["state", "updated_at"])
    _create_note(transaction_reconciliation, user, note)
    return transaction_reconciliation


def resolve_exception(*, transaction_reconciliation, user, note=""):
    """Resolve an exception through the existing explicit state machine."""
    if transaction_reconciliation.state == TransactionState.EXCEPTION:
        transaction_reconciliation.transition_to(TransactionState.UNDER_REVIEW)
    if transaction_reconciliation.state != TransactionState.UNDER_REVIEW:
        raise ValidationError("Only an exception under review can be resolved.")
    transaction_reconciliation.transition_to(TransactionState.RESOLVED)
    transaction_reconciliation.save(update_fields=["state", "updated_at"])
    _create_note(transaction_reconciliation, user, note)
    return transaction_reconciliation


def add_investigation_note(*, transaction_reconciliation, user, content):
    """Persist a review note attached to a tenant-scoped transaction state."""
    return ReconciliationInvestigationNote.objects.create(
        transaction_reconciliation=transaction_reconciliation,
        author=user,
        content=content,
    )
