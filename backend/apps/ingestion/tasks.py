"""
Celery tasks for asynchronous import processing.
"""

import logging

from celery import shared_task
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=2, default_retry_delay=30)
def process_import_task(self, import_record_id: str):
    """
    Async task: parse, validate, and persist an imported file.

    Steps:
    1. Download file from storage
    2. Parse CSV/XLSX
    3. Validate rows
    4. Record errors
    5. Update import status
    """
    from apps.ingestion.models import (
        CanonicalTransaction,
        ImportRecord,
        ImportRowError,
        ImportStatus,
    )
    from apps.ingestion.normalization import normalize_row
    from apps.ingestion.parsers import RowLimitExceeded, parse_file, validate_dataframe
    from apps.ingestion.storage import get_storage_backend

    try:
        record = ImportRecord.objects.get(pk=import_record_id)
    except ImportRecord.DoesNotExist:
        logger.error("ImportRecord %s not found", import_record_id)
        return

    if record.status in (ImportStatus.COMPLETED, ImportStatus.PARTIALLY_COMPLETED):
        logger.info("Import %s was already processed; skipping duplicate task", import_record_id)
        return

    # Update status to PROCESSING
    record.status = ImportStatus.PROCESSING
    record.processing_started_at = timezone.now()
    record.celery_task_id = self.request.id or ""
    record.save(update_fields=["status", "processing_started_at", "celery_task_id"])

    try:
        # 1. Download file
        storage = get_storage_backend()
        file_content = storage.download(record.storage_path)

        # 2. Parse
        df = parse_file(file_content, record.file_type)
        record.total_rows = len(df)

        # 3. Validate
        errors = validate_dataframe(df)

        # 4. Build row errors and canonical records. A row can have many field
        # errors but is rejected only once.
        row_errors = []
        for err in errors:
            row_errors.append(ImportRowError(
                import_record=record,
                row_number=err.get("row", 0),
                field_name=err.get("field", ""),
                error_type=err.get("type", "validation"),
                error_message=err.get("error", ""),
                raw_value=str(err.get("raw_value", "")),
            ))

        # 5. Update counts and status
        has_structure_error = any(err.get("row", 0) == 0 for err in errors)
        invalid_row_numbers = {
            err["row"] for err in errors if err.get("row", 0) > 0
        }
        record.rejected_rows = (
            record.total_rows if has_structure_error else len(invalid_row_numbers)
        )
        record.valid_rows = max(0, record.total_rows - record.rejected_rows)
        record.processing_completed_at = timezone.now()

        transactions = []
        if not has_structure_error:
            for index, row in df.iterrows():
                source_row_number = index + 2
                if source_row_number in invalid_row_numbers:
                    continue
                normalized = normalize_row(row)
                transactions.append(CanonicalTransaction(
                    organization=record.organization,
                    import_record=record,
                    source_row_number=source_row_number,
                    source=record.source,
                    external_id=normalized.external_id,
                    transaction_date=normalized.transaction_date,
                    amount=normalized.amount,
                    currency=normalized.currency,
                    reference=normalized.reference,
                    normalized_reference=normalized.normalized_reference,
                    description=normalized.description,
                    counterparty=normalized.counterparty,
                    normalized_counterparty=normalized.normalized_counterparty,
                    raw_data=normalized.raw_data,
                ))

        if errors and record.valid_rows == 0:
            record.status = ImportStatus.FAILED
            record.error_message = f"{len(errors)} validation error(s). No valid rows."
        elif errors:
            record.status = ImportStatus.PARTIALLY_COMPLETED
            record.error_message = (
                f"{len(errors)} validation error(s) across "
                f"{record.rejected_rows} rejected row(s)."
            )
        else:
            record.status = ImportStatus.COMPLETED

        # Recreating these derived records in one transaction makes task retries
        # idempotent and avoids duplicate rows/errors after a partial failure.
        with transaction.atomic():
            ImportRowError.objects.filter(import_record=record).delete()
            CanonicalTransaction.objects.filter(import_record=record).delete()
            if row_errors:
                ImportRowError.objects.bulk_create(row_errors, batch_size=1000)
            if transactions:
                CanonicalTransaction.objects.bulk_create(transactions, batch_size=1000)
            record.save()
        logger.info(
            "Import %s completed: %d valid, %d rejected out of %d total",
            import_record_id, record.valid_rows, record.rejected_rows, record.total_rows,
        )

    except RowLimitExceeded as exc:
        record.status = ImportStatus.FAILED
        record.processing_completed_at = timezone.now()
        record.error_message = str(exc)
        record.save(update_fields=["status", "processing_completed_at", "error_message"])
        logger.warning("Import %s rejected: %s", import_record_id, exc)
    except Exception as exc:
        record.status = ImportStatus.FAILED
        record.processing_completed_at = timezone.now()
        record.error_message = str(exc)[:2000]
        record.save(update_fields=["status", "processing_completed_at", "error_message"])
        logger.exception("Import %s failed", import_record_id)
        raise self.retry(exc=exc)
