"""
Ingestion models — ImportRecord and ImportError tracking.
"""

import hashlib

from django.conf import settings
from django.db import models

from apps.common.models import BaseModel


class ImportStatus(models.TextChoices):
    PENDING = "PENDING", "Pending"
    VALIDATING = "VALIDATING", "Validating"
    PROCESSING = "PROCESSING", "Processing"
    COMPLETED = "COMPLETED", "Completed"
    FAILED = "FAILED", "Failed"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED", "Partially Completed"


class ImportSource(models.TextChoices):
    ERP = "ERP", "ERP System"
    BANK = "BANK", "Bank Statement"
    ACCOUNTING = "ACCOUNTING", "Accounting System"
    OTHER = "OTHER", "Other"


class ImportRecord(BaseModel):
    """
    Tracks a file upload and its processing lifecycle.

    Stores metadata about the uploaded file, processing status,
    row counts, and error information.
    """

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="imports",
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="imports",
    )

    # File metadata
    original_filename = models.CharField(max_length=512)
    file_type = models.CharField(max_length=10)  # csv, xlsx
    file_size = models.PositiveIntegerField(help_text="File size in bytes")
    file_checksum = models.CharField(max_length=64, help_text="SHA-256 checksum")
    storage_path = models.CharField(
        max_length=1024, blank=True, default="",
        help_text="Path in Supabase Storage",
    )

    # Source classification
    source = models.CharField(
        max_length=20,
        choices=ImportSource.choices,
        default=ImportSource.OTHER,
    )

    # Processing status
    status = models.CharField(
        max_length=25,
        choices=ImportStatus.choices,
        default=ImportStatus.PENDING,
    )
    celery_task_id = models.CharField(max_length=255, blank=True, default="")

    # Row counts
    total_rows = models.PositiveIntegerField(default=0)
    valid_rows = models.PositiveIntegerField(default=0)
    rejected_rows = models.PositiveIntegerField(default=0)

    # Timestamps
    processing_started_at = models.DateTimeField(null=True, blank=True)
    processing_completed_at = models.DateTimeField(null=True, blank=True)

    # Error summary
    error_message = models.TextField(blank=True, default="")

    class Meta:
        db_table = "import_records"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.original_filename} ({self.status})"

    @staticmethod
    def compute_checksum(file_obj) -> str:
        """Compute SHA-256 checksum of an uploaded file."""
        sha256 = hashlib.sha256()
        file_obj.seek(0)
        for chunk in file_obj.chunks(8192):
            sha256.update(chunk)
        file_obj.seek(0)
        return sha256.hexdigest()


class ImportRowError(BaseModel):
    """
    Tracks individual row-level errors during import processing.
    """

    import_record = models.ForeignKey(
        ImportRecord,
        on_delete=models.CASCADE,
        related_name="row_errors",
    )
    row_number = models.PositiveIntegerField()
    field_name = models.CharField(max_length=255, blank=True, default="")
    error_type = models.CharField(max_length=50)  # validation, parsing, type_error
    error_message = models.TextField()
    raw_value = models.TextField(blank=True, default="")

    class Meta:
        db_table = "import_row_errors"
        ordering = ["row_number"]

    def __str__(self):
        return f"Row {self.row_number}: {self.error_type} - {self.error_message}"




class CanonicalTransaction(BaseModel):
    """
    A normalized transaction persisted from a valid import row.

    This is intentionally limited to ingestion's canonical representation.  It
    provides stable, tenant-scoped input for a future reconciliation service;
    it does not contain reconciliation state or matching behaviour.
    """

    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="canonical_transactions",
    )
    import_record = models.ForeignKey(
        ImportRecord,
        on_delete=models.CASCADE,
        related_name="canonical_transactions",
    )

    # Source provenance
    source_row_number = models.PositiveIntegerField()
    source = models.CharField(max_length=20, choices=ImportSource.choices)
    raw_data = models.JSONField(default=dict)

    # Canonical transaction fields
    external_id = models.CharField(max_length=255, blank=True, default="")
    transaction_date = models.DateField(db_index=True)
    amount = models.DecimalField(max_digits=24, decimal_places=6)
    currency = models.CharField(max_length=3, blank=True, default="")
    reference = models.CharField(max_length=512, blank=True, default="")
    normalized_reference = models.CharField(
        max_length=512, blank=True, default="", db_index=True
    )
    description = models.TextField(blank=True, default="")
    counterparty = models.CharField(max_length=512, blank=True, default="")
    normalized_counterparty = models.CharField(
        max_length=512, blank=True, default="", db_index=True
    )

    class Meta:
        db_table = "canonical_transactions"
        ordering = ["transaction_date", "source_row_number"]
        constraints = [
            models.UniqueConstraint(
                fields=("import_record", "source_row_number"),
                name="unique_import_source_row",
            ),
        ]

    def __str__(self):
        return f"{self.transaction_date} {self.amount} ({self.source})"
