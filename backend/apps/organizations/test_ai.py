from unittest.mock import Mock
from datetime import date
from decimal import Decimal

import pytest
from django.test import override_settings
from rest_framework import status

from apps.ingestion.models import CanonicalTransaction, ImportRecord, ImportSource
from apps.reconciliation.models import (
    MatchCandidate,
    ReconciliationRun,
    TransactionReconciliation,
    TransactionState,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def assist_url(organization):
    return f"/api/v1/organizations/{organization.id}/ai/assist/"


@pytest.fixture
def candidate_state(organization, user):
    source_import = ImportRecord.objects.create(
        organization=organization, uploaded_by=user, original_filename="bank.csv",
        file_type="csv", file_size=12, file_checksum="assistant-source", source=ImportSource.BANK,
    )
    target_import = ImportRecord.objects.create(
        organization=organization, uploaded_by=user, original_filename="erp.csv",
        file_type="csv", file_size=12, file_checksum="assistant-target", source=ImportSource.ERP,
    )
    source = CanonicalTransaction.objects.create(
        organization=organization, import_record=source_import, source_row_number=2,
        source=ImportSource.BANK, transaction_date=date(2026, 10, 2),
        amount=Decimal("760.50"), currency="USD", reference="PAY-778",
        normalized_reference="pay778", counterparty="Northwind Traders",
        normalized_counterparty="northwind traders",
    )
    target = CanonicalTransaction.objects.create(
        organization=organization, import_record=target_import, source_row_number=2,
        source=ImportSource.ERP, transaction_date=date(2026, 10, 2),
        amount=Decimal("760.50"), currency="USD", reference="INV-1002",
        normalized_reference="inv1002", counterparty="Northwind Traders",
        normalized_counterparty="northwind traders",
    )
    run = ReconciliationRun.objects.create(
        organization=organization, initiated_by=user, source_import=source_import,
        target_import=target_import, status="COMPLETED", total_source=1, total_target=1,
    )
    state = TransactionReconciliation.objects.create(
        run=run, transaction=source, side="SOURCE", state=TransactionState.CANDIDATE,
    )
    MatchCandidate.objects.create(
        run=run, source_transaction=source, target_transaction=target, score=Decimal("0.6000"),
        reference_score=Decimal("0"), amount_score=Decimal("1"), date_score=Decimal("1"),
        counterparty_score=Decimal("1"), evidence={
            "reference": {"method": "none"}, "amount": {"method": "exact"},
            "date": {"method": "exact"}, "counterparty": {"method": "exact"},
        },
    )
    return run, state


class TestAssistantAPI:
    def test_requires_authentication(self, api_client, assist_url):
        response = api_client.post(assist_url, {"question": "Summarize activity."})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_enforces_organization_membership(self, admin_client, other_organization):
        response = admin_client.post(
            f"/api/v1/organizations/{other_organization.id}/ai/assist/",
            {"question": "Summarize activity."},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    @override_settings(AI_PROVIDER="groq", AI_API_KEY="test-key", AI_MODEL="test-model")
    def test_returns_provider_explanation_for_authorized_member(
        self, admin_client, assist_url, monkeypatch
    ):
        provider_response = Mock()
        provider_response.raise_for_status.return_value = None
        provider_response.json.return_value = {
            "choices": [{"message": {"content": "No transactions need attention."}}]
        }
        request = Mock(return_value=provider_response)
        monkeypatch.setattr("apps.organizations.ai_assistant.requests.post", request)

        response = admin_client.post(assist_url, {"question": "What needs attention?"})

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {"answer": "No transactions need attention."}
        assert request.call_args.kwargs["headers"]["Authorization"] == "Bearer test-key"

    @override_settings(AI_API_KEY="")
    def test_reports_missing_api_key(self, admin_client, assist_url):
        response = admin_client.post(assist_url, {"question": "Summarize activity."})
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    @override_settings(AI_API_KEY="")
    def test_returns_authoritative_candidate_evidence_without_provider(
        self, admin_client, assist_url, candidate_state
    ):
        run, state = candidate_state
        response = admin_client.post(assist_url, {
            "question": "Why is PAY-778 a candidate?",
            "run_id": str(run.id),
            "transaction_reconciliation_id": str(state.id),
        })
        assert response.status_code == status.HTTP_200_OK
        assert "Amount: USD 760.50" in response.data["answer"]
        assert "Reference: PAY-778 ↔ INV-1002 — different" in response.data["answer"]
        assert "Composite candidate score: 60.00%" in response.data["answer"]

    @override_settings(AI_API_KEY="")
    def test_summarizes_attention_from_run_states(
        self, admin_client, assist_url, candidate_state
    ):
        run, _ = candidate_state
        response = admin_client.post(assist_url, {
            "question": "What transactions need attention?", "run_id": str(run.id),
        })
        assert response.status_code == status.HTTP_200_OK
        assert "Candidates: 1" in response.data["answer"]
        assert "Highest priority: PAY-778" in response.data["answer"]

    @override_settings(AI_API_KEY="")
    def test_reports_latest_import_timestamp(self, admin_client, assist_url, candidate_state):
        candidate_state
        response = admin_client.post(assist_url, {"question": "What is the time of the latest import?"})
        assert response.status_code == status.HTTP_200_OK
        assert "Uploaded at:" in response.data["answer"]
