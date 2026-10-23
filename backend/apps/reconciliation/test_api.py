"""API tests for reconciliation execution, results, and human review."""

from datetime import date
from decimal import Decimal

import pytest
from rest_framework import status

from apps.ingestion.models import CanonicalTransaction, ImportRecord, ImportSource
from apps.organizations.models import MembershipRole
from apps.reconciliation.models import (
    MatchCandidate,
    ReconciliationRun,
    TransactionReconciliation,
    TransactionState,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def reconciliation_inputs(organization, user):
    source_import = ImportRecord.objects.create(
        organization=organization, uploaded_by=user, original_filename="erp.csv",
        file_type="csv", file_size=100, file_checksum="api-source", source=ImportSource.ERP,
    )
    target_import = ImportRecord.objects.create(
        organization=organization, uploaded_by=user, original_filename="bank.csv",
        file_type="csv", file_size=100, file_checksum="api-target", source=ImportSource.BANK,
    )
    source = CanonicalTransaction.objects.create(
        organization=organization, import_record=source_import, source_row_number=2,
        source=ImportSource.ERP, transaction_date=date(2024, 1, 15),
        amount=Decimal("100.50"), currency="USD", reference="INV-001",
        normalized_reference="inv001", counterparty="Acme Corp",
        normalized_counterparty="acme corp",
    )
    target = CanonicalTransaction.objects.create(
        organization=organization, import_record=target_import, source_row_number=2,
        source=ImportSource.BANK, transaction_date=date(2024, 1, 15),
        amount=Decimal("100.50"), currency="USD", reference="INV-001",
        normalized_reference="inv001", counterparty="Acme Corp",
        normalized_counterparty="acme corp",
    )
    return source_import, target_import, source, target


def create_run(client, organization, source_import, target_import):
    response = client.post(
        f"/api/v1/organizations/{organization.id}/reconciliation/runs/",
        {"source_import": str(source_import.id), "target_import": str(target_import.id)},
    )
    assert response.status_code == status.HTTP_201_CREATED
    return ReconciliationRun.objects.get(pk=response.data["id"])


class TestReconciliationAPI:
    def test_runs_require_authentication(self, api_client, organization):
        response = api_client.get(
            f"/api/v1/organizations/{organization.id}/reconciliation/runs/"
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_admin_creates_and_runs_reconciliation(
        self, admin_client, organization, reconciliation_inputs
    ):
        source_import, target_import, _, _ = reconciliation_inputs
        run = create_run(admin_client, organization, source_import, target_import)
        assert run.status == "COMPLETED"
        assert run.total_source == 1
        assert run.total_target == 1
        assert run.matched_count == 1

    def test_analyst_cannot_start_run(
        self, analyst_client, organization, reconciliation_inputs
    ):
        source_import, target_import, _, _ = reconciliation_inputs
        response = analyst_client.post(
            f"/api/v1/organizations/{organization.id}/reconciliation/runs/",
            {"source_import": str(source_import.id), "target_import": str(target_import.id)},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_results_and_decimal_transaction_values_are_serialized(
        self, admin_client, organization, reconciliation_inputs
    ):
        source_import, target_import, _, _ = reconciliation_inputs
        run = create_run(admin_client, organization, source_import, target_import)
        response = admin_client.get(
            f"/api/v1/organizations/{organization.id}/reconciliation/runs/{run.id}/results/"
        )
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["results"]) == 2
        assert response.data["results"][0]["transaction"]["amount"] == "100.500000"

    def test_candidate_evidence_is_available(
        self, admin_client, organization, reconciliation_inputs
    ):
        source_import, target_import, _, _ = reconciliation_inputs
        run = create_run(admin_client, organization, source_import, target_import)
        candidate = MatchCandidate.objects.get(run=run)
        response = admin_client.get(
            f"/api/v1/organizations/{organization.id}/reconciliation/runs/{run.id}/candidates/{candidate.id}/"
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.data["evidence"]["reference"]["method"] == "exact"
        assert response.data["score"] == "1.0000"

    def test_deterministic_match_can_be_confirmed(
        self, admin_client, organization, reconciliation_inputs
    ):
        source_import, target_import, source, _ = reconciliation_inputs
        run = create_run(admin_client, organization, source_import, target_import)
        source_state = TransactionReconciliation.objects.get(run=run, transaction=source)
        candidate = MatchCandidate.objects.get(run=run, source_transaction=source)
        response = admin_client.post(
            f"/api/v1/organizations/{organization.id}/reconciliation/runs/{run.id}/transactions/{source_state.id}/confirm/",
            {"candidate_id": str(candidate.id)},
        )
        assert response.status_code == status.HTTP_200_OK
        candidate.refresh_from_db()
        assert candidate.review_status == "CONFIRMED"

    def test_cross_tenant_run_access_is_denied(
        self, admin_client, other_organization, other_user, create_membership
    ):
        create_membership(other_user, other_organization, MembershipRole.ADMIN)
        other_run = ReconciliationRun.objects.create(
            organization=other_organization, initiated_by=other_user,
            source_import=ImportRecord.objects.create(
                organization=other_organization, uploaded_by=other_user,
                original_filename="other-source.csv", file_type="csv", file_size=1,
                file_checksum="other-source", source=ImportSource.ERP,
            ),
            target_import=ImportRecord.objects.create(
                organization=other_organization, uploaded_by=other_user,
                original_filename="other-target.csv", file_type="csv", file_size=1,
                file_checksum="other-target", source=ImportSource.BANK,
            ),
        )
        response = admin_client.get(
            f"/api/v1/organizations/{other_organization.id}/reconciliation/runs/{other_run.id}/"
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestReconciliationWorkflowAPI:
    @pytest.fixture
    def candidate_state(self, organization, user, reconciliation_inputs):
        source_import, target_import, source, target = reconciliation_inputs
        run = ReconciliationRun.objects.create(
            organization=organization, initiated_by=user,
            source_import=source_import, target_import=target_import,
        )
        source_state = TransactionReconciliation.objects.create(
            run=run, transaction=source, side="SOURCE", state=TransactionState.CANDIDATE,
        )
        TransactionReconciliation.objects.create(
            run=run, transaction=target, side="TARGET", state=TransactionState.UNMATCHED,
        )
        candidate = MatchCandidate.objects.create(
            run=run, source_transaction=source, target_transaction=target,
            score=Decimal("0.8000"), reference_score=Decimal("0.8000"),
            amount_score=Decimal("1.0000"), date_score=Decimal("1.0000"),
            counterparty_score=Decimal("1.0000"), evidence={"reference": {"method": "normalized"}},
        )
        return run, source_state, candidate

    def test_analyst_can_confirm_candidate(
        self, analyst_client, organization, candidate_state
    ):
        run, source_state, candidate = candidate_state
        response = analyst_client.post(
            f"/api/v1/organizations/{organization.id}/reconciliation/runs/{run.id}/transactions/{source_state.id}/confirm/",
            {"candidate_id": str(candidate.id), "note": "Verified against bank statement."},
        )
        assert response.status_code == status.HTTP_200_OK
        source_state.refresh_from_db()
        candidate.refresh_from_db()
        assert source_state.state == TransactionState.MATCHED
        assert candidate.is_selected is True
        assert candidate.review_status == "CONFIRMED"
        assert response.data["investigation_notes"][0]["content"] == "Verified against bank statement."

    def test_rejecting_only_candidate_returns_to_unmatched(
        self, analyst_client, organization, candidate_state
    ):
        run, source_state, candidate = candidate_state
        response = analyst_client.post(
            f"/api/v1/organizations/{organization.id}/reconciliation/runs/{run.id}/transactions/{source_state.id}/reject/",
            {"candidate_id": str(candidate.id)},
        )
        assert response.status_code == status.HTTP_200_OK
        source_state.refresh_from_db()
        candidate.refresh_from_db()
        assert source_state.state == TransactionState.UNMATCHED
        assert candidate.review_status == "REJECTED"

    def test_invalid_transition_is_rejected(self, analyst_client, organization, candidate_state):
        run, source_state, _ = candidate_state
        source_state.state = TransactionState.RESOLVED
        source_state.save(update_fields=["state"])
        response = analyst_client.post(
            f"/api/v1/organizations/{organization.id}/reconciliation/runs/{run.id}/transactions/{source_state.id}/exception/",
            {},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_exception_can_be_resolved_and_noted(
        self, analyst_client, organization, candidate_state
    ):
        run, source_state, _ = candidate_state
        exception = analyst_client.post(
            f"/api/v1/organizations/{organization.id}/reconciliation/runs/{run.id}/transactions/{source_state.id}/exception/",
            {"note": "Needs supporting document."},
        )
        assert exception.status_code == status.HTTP_200_OK
        response = analyst_client.post(
            f"/api/v1/organizations/{organization.id}/reconciliation/runs/{run.id}/transactions/{source_state.id}/resolve/",
            {"note": "Document received."},
        )
        assert response.status_code == status.HTTP_200_OK
        source_state.refresh_from_db()
        assert source_state.state == TransactionState.RESOLVED
        assert len(response.data["investigation_notes"]) == 2

    def test_auditor_cannot_perform_workflow_actions(
        self, api_client, organization, other_user, create_membership, candidate_state
    ):
        create_membership(other_user, organization, MembershipRole.AUDITOR)
        api_client.force_authenticate(user=other_user)
        run, source_state, candidate = candidate_state
        response = api_client.post(
            f"/api/v1/organizations/{organization.id}/reconciliation/runs/{run.id}/transactions/{source_state.id}/confirm/",
            {"candidate_id": str(candidate.id)},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_analyst_can_add_investigation_note(
        self, analyst_client, organization, candidate_state
    ):
        run, source_state, _ = candidate_state
        response = analyst_client.post(
            f"/api/v1/organizations/{organization.id}/reconciliation/runs/{run.id}/transactions/{source_state.id}/notes/",
            {"content": "Investigating reference formatting."},
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["content"] == "Investigating reference formatting."
