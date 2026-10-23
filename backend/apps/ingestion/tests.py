"""
Tests for the ingestion app — upload validation, parsing, async processing, tenant isolation.
"""

import io
from decimal import Decimal
import pytest
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework import status

from apps.ingestion.models import CanonicalTransaction, ImportRecord, ImportStatus
from apps.ingestion.parsers import (
    MAX_ROWS,
    RowLimitExceeded,
    parse_csv,
    parse_file,
    validate_dataframe,
)
from apps.ingestion.validators import validate_upload
from apps.organizations.models import MembershipRole

pytestmark = pytest.mark.django_db


# ─── Parser tests (unit, no Django) ──────────────────────────────────

class TestParsers:
    def test_parse_csv_basic(self):
        csv_content = b"Transaction Date,Amount,Reference\n2024-01-15,100.50,REF001\n"
        df = parse_csv(csv_content)
        assert len(df) == 1
        assert "transaction_date" in df.columns
        assert "amount" in df.columns

    def test_parse_csv_normalizes_columns(self):
        csv_content = b"Transaction Date,Amount (USD),Counter-Party\n2024-01-15,100,ACME\n"
        df = parse_csv(csv_content)
        assert "transaction_date" in df.columns
        assert "amount_(usd)" in df.columns
        assert "counter_party" in df.columns

    def test_parse_csv_empty_file(self):
        csv_content = b""
        # pandas raises EmptyDataError for empty content
        import pandas as pd
        with pytest.raises(pd.errors.EmptyDataError):
            parse_csv(csv_content)

    def test_parse_file_unsupported_type(self):
        with pytest.raises(ValueError, match="Unsupported file type"):
            parse_file(b"content", "pdf")

    def test_parse_csv_rejects_files_above_row_limit(self):
        csv_content = (
            b"transaction_date,amount\n"
            + b"2024-01-15,100.00\n" * (MAX_ROWS + 1)
        )
        with pytest.raises(RowLimitExceeded, match="100,000"):
            parse_csv(csv_content)

    def test_validate_dataframe_valid(self):
        import pandas as pd
        df = pd.DataFrame({
            "transaction_date": ["2024-01-15"],
            "amount": ["100.50"],
            "reference": ["REF001"],
        })
        errors = validate_dataframe(df)
        assert len(errors) == 0

    def test_validate_dataframe_missing_required_columns(self):
        import pandas as pd
        df = pd.DataFrame({"description": ["something"]})
        errors = validate_dataframe(df)
        assert len(errors) == 1
        assert errors[0]["type"] == "structure"

    def test_validate_dataframe_invalid_amount(self):
        import pandas as pd
        df = pd.DataFrame({
            "transaction_date": ["2024-01-15"],
            "amount": ["not-a-number"],
        })
        errors = validate_dataframe(df)
        assert any(e["field"] == "amount" for e in errors)

    def test_validate_dataframe_rejects_non_finite_decimal_amount(self):
        import pandas as pd
        df = pd.DataFrame({
            "transaction_date": ["2024-01-15"],
            "amount": ["NaN"],
        })
        errors = validate_dataframe(df)
        assert errors[0]["field"] == "amount"
        assert "finite" in errors[0]["error"]

    def test_validate_dataframe_empty_date(self):
        import pandas as pd
        df = pd.DataFrame({
            "transaction_date": [""],
            "amount": ["100.00"],
        })
        errors = validate_dataframe(df)
        assert any(e["field"] == "transaction_date" for e in errors)

    def test_validate_dataframe_empty(self):
        import pandas as pd
        df = pd.DataFrame()
        errors = validate_dataframe(df)
        assert len(errors) == 1
        assert errors[0]["type"] == "structure"


# ─── Upload validation tests ────────────────────────────────────────

class TestUploadValidation:
    def test_valid_csv_upload(self):
        file = SimpleUploadedFile("data.csv", b"a,b\n1,2\n", content_type="text/csv")
        result = validate_upload(file)
        assert result["valid"] is True
        assert result["file_type"] == "csv"

    def test_valid_xlsx_upload(self):
        # Create a minimal valid XLSX (ZIP with PK header)
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["transaction_date", "amount"])
        ws.append(["2024-01-15", "100.50"])
        buffer = io.BytesIO()
        wb.save(buffer)
        buffer.seek(0)
        file = SimpleUploadedFile("data.xlsx", buffer.read(),
                                   content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        result = validate_upload(file)
        assert result["valid"] is True
        assert result["file_type"] == "xlsx"

    def test_reject_unsupported_extension(self):
        file = SimpleUploadedFile("data.pdf", b"fake", content_type="application/pdf")
        result = validate_upload(file)
        assert result["valid"] is False
        assert any("not supported" in e for e in result["errors"])

    def test_reject_empty_file(self):
        file = SimpleUploadedFile("data.csv", b"", content_type="text/csv")
        file.size = 0
        result = validate_upload(file)
        assert result["valid"] is False

    def test_reject_oversized_file(self):
        file = SimpleUploadedFile("data.csv", b"x" * 100, content_type="text/csv")
        file.size = 20 * 1024 * 1024  # 20 MB
        result = validate_upload(file)
        assert result["valid"] is False
        assert any("exceeds" in e for e in result["errors"])

    def test_reject_xlsx_wrong_magic_bytes(self):
        file = SimpleUploadedFile("data.xlsx", b"This is not xlsx",
                                   content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        result = validate_upload(file)
        assert result["valid"] is False
        assert any("does not match" in e for e in result["errors"])


# ─── API integration tests ──────────────────────────────────────────

class TestFileUploadAPI:
    @patch("apps.ingestion.views.process_import_task.delay")
    def test_upload_csv_success(self, mock_task, admin_client, organization):
        csv_content = b"transaction_date,amount,reference\n2024-01-15,100.50,REF001\n"
        file = SimpleUploadedFile("test.csv", csv_content, content_type="text/csv")

        response = admin_client.post(
            f"/api/v1/organizations/{organization.id}/imports/upload/",
            {"file": file, "source": "ERP"},
            format="multipart",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["original_filename"] == "test.csv"
        assert response.data["status"] == "PENDING"
        mock_task.assert_called_once()

    @patch("apps.ingestion.views.process_import_task.delay")
    def test_upload_duplicate_rejected(self, mock_task, admin_client, organization):
        csv_content = b"transaction_date,amount\n2024-01-15,100.50\n"
        file1 = SimpleUploadedFile("test1.csv", csv_content, content_type="text/csv")
        file2 = SimpleUploadedFile("test2.csv", csv_content, content_type="text/csv")

        admin_client.post(
            f"/api/v1/organizations/{organization.id}/imports/upload/",
            {"file": file1}, format="multipart",
        )
        response = admin_client.post(
            f"/api/v1/organizations/{organization.id}/imports/upload/",
            {"file": file2}, format="multipart",
        )
        assert response.status_code == status.HTTP_409_CONFLICT

    def test_upload_unsupported_format(self, admin_client, organization):
        file = SimpleUploadedFile("data.pdf", b"fake pdf", content_type="application/pdf")
        response = admin_client.post(
            f"/api/v1/organizations/{organization.id}/imports/upload/",
            {"file": file}, format="multipart",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_upload_requires_auth(self, api_client, organization):
        file = SimpleUploadedFile("test.csv", b"a,b\n1,2\n", content_type="text/csv")
        response = api_client.post(
            f"/api/v1/organizations/{organization.id}/imports/upload/",
            {"file": file}, format="multipart",
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestImportListAPI:
    def test_list_imports_org_scoped(self, admin_client, organization,
                                      other_organization, user, create_membership):
        # Create imports in two orgs
        ImportRecord.objects.create(
            organization=organization, uploaded_by=user,
            original_filename="org1.csv", file_type="csv",
            file_size=100, file_checksum="abc123",
        )
        ImportRecord.objects.create(
            organization=other_organization, uploaded_by=user,
            original_filename="org2.csv", file_type="csv",
            file_size=100, file_checksum="def456",
        )

        response = admin_client.get(
            f"/api/v1/organizations/{organization.id}/imports/"
        )
        assert response.status_code == status.HTTP_200_OK
        filenames = [r["original_filename"] for r in response.data["results"]]
        assert "org1.csv" in filenames
        assert "org2.csv" not in filenames  # Tenant isolation


class TestImportTenantIsolation:
    def test_cannot_access_other_org_imports(self, authenticated_client,
                                              other_organization, other_user,
                                              create_membership):
        create_membership(other_user, other_organization, MembershipRole.ADMIN)
        ImportRecord.objects.create(
            organization=other_organization, uploaded_by=other_user,
            original_filename="secret.csv", file_type="csv",
            file_size=100, file_checksum="secret123",
        )

        response = authenticated_client.get(
            f"/api/v1/organizations/{other_organization.id}/imports/"
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


# ─── Celery task tests (eager mode) ─────────────────────────────────

class TestProcessImportTask:
    @patch("apps.ingestion.storage.get_storage_backend")
    def test_process_valid_csv(self, mock_get_backend, admin_client, organization, user):
        csv_content = (
            b"transaction_date,amount,reference,counterparty,currency\n"
            b"2024-01-15,100.50,REF-001,Acme,usd\n"
            b"2024-01-16,200.00,REF002,Other Co,usd\n"
        )

        mock_backend = mock_get_backend.return_value
        mock_backend.download.return_value = csv_content

        record = ImportRecord.objects.create(
            organization=organization, uploaded_by=user,
            original_filename="valid.csv", file_type="csv",
            file_size=len(csv_content), file_checksum="validhash",
            storage_path="imports/test/valid.csv",
            status=ImportStatus.PENDING,
        )

        from apps.ingestion.tasks import process_import_task
        process_import_task(str(record.id))

        record.refresh_from_db()
        assert record.status == ImportStatus.COMPLETED
        assert record.total_rows == 2
        assert record.valid_rows == 2
        assert record.rejected_rows == 0
        transactions = CanonicalTransaction.objects.filter(import_record=record)
        assert transactions.count() == 2
        first = transactions.get(source_row_number=2)
        assert first.amount == Decimal("100.500000")
        assert first.normalized_reference == "ref001"
        assert first.normalized_counterparty == "acme"
        assert first.raw_data["currency"] == "usd"

    @patch("apps.ingestion.storage.get_storage_backend")
    def test_process_csv_with_errors(self, mock_get_backend, organization, user):
        csv_content = b"transaction_date,amount\n2024-01-15,not-a-number\n"

        mock_backend = mock_get_backend.return_value
        mock_backend.download.return_value = csv_content

        record = ImportRecord.objects.create(
            organization=organization, uploaded_by=user,
            original_filename="bad.csv", file_type="csv",
            file_size=len(csv_content), file_checksum="badhash",
            storage_path="imports/test/bad.csv",
            status=ImportStatus.PENDING,
        )

        from apps.ingestion.tasks import process_import_task
        process_import_task(str(record.id))

        record.refresh_from_db()
        assert record.status == ImportStatus.FAILED
        assert record.rejected_rows > 0
        assert record.row_errors.count() > 0

    @patch("apps.ingestion.storage.get_storage_backend")
    def test_multiple_field_errors_reject_one_row_and_persist_valid_rows(
        self, mock_get_backend, organization, user
    ):
        csv_content = (
            b"transaction_date,amount,reference\n"
            b",not-a-number,BAD\n"
            b"2024-01-16,25.00,GOOD\n"
        )
        mock_get_backend.return_value.download.return_value = csv_content
        record = ImportRecord.objects.create(
            organization=organization, uploaded_by=user,
            original_filename="mixed.csv", file_type="csv",
            file_size=len(csv_content), file_checksum="mixedhash",
            storage_path="imports/test/mixed.csv", status=ImportStatus.PENDING,
        )

        from apps.ingestion.tasks import process_import_task
        process_import_task(str(record.id))

        record.refresh_from_db()
        assert record.status == ImportStatus.PARTIALLY_COMPLETED
        assert record.total_rows == 2
        assert record.rejected_rows == 1
        assert record.valid_rows == 1
        assert record.row_errors.count() == 2
        assert CanonicalTransaction.objects.filter(import_record=record).count() == 1

    @patch("apps.ingestion.storage.get_storage_backend")
    def test_processing_is_idempotent_after_completion(
        self, mock_get_backend, organization, user
    ):
        csv_content = b"transaction_date,amount\n2024-01-15,100.00\n"
        mock_get_backend.return_value.download.return_value = csv_content
        record = ImportRecord.objects.create(
            organization=organization, uploaded_by=user,
            original_filename="once.csv", file_type="csv",
            file_size=len(csv_content), file_checksum="oncehash",
            storage_path="imports/test/once.csv", status=ImportStatus.PENDING,
        )

        from apps.ingestion.tasks import process_import_task
        process_import_task(str(record.id))
        process_import_task(str(record.id))

        assert CanonicalTransaction.objects.filter(import_record=record).count() == 1

    @patch("apps.ingestion.storage.get_storage_backend")
    def test_process_rejects_row_limit_without_persisting_transactions(
        self, mock_get_backend, organization, user
    ):
        csv_content = (
            b"transaction_date,amount\n"
            + b"2024-01-15,100.00\n" * (MAX_ROWS + 1)
        )
        mock_get_backend.return_value.download.return_value = csv_content
        record = ImportRecord.objects.create(
            organization=organization, uploaded_by=user,
            original_filename="too-many.csv", file_type="csv",
            file_size=len(csv_content), file_checksum="rowlimithash",
            storage_path="imports/test/too-many.csv", status=ImportStatus.PENDING,
        )

        from apps.ingestion.tasks import process_import_task
        process_import_task(str(record.id))

        record.refresh_from_db()
        assert record.status == ImportStatus.FAILED
        assert "100,000" in record.error_message
        assert CanonicalTransaction.objects.filter(import_record=record).count() == 0
