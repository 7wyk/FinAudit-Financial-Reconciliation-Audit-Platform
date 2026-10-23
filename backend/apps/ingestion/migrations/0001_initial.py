import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("organizations", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ImportRecord",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("original_filename", models.CharField(max_length=512)),
                ("file_type", models.CharField(max_length=10)),
                ("file_size", models.PositiveIntegerField(help_text="File size in bytes")),
                ("file_checksum", models.CharField(help_text="SHA-256 checksum", max_length=64)),
                ("storage_path", models.CharField(blank=True, default="", help_text="Path in Supabase Storage", max_length=1024)),
                ("source", models.CharField(choices=[("ERP", "ERP System"), ("BANK", "Bank Statement"), ("ACCOUNTING", "Accounting System"), ("OTHER", "Other")], default="OTHER", max_length=20)),
                ("status", models.CharField(choices=[("PENDING", "Pending"), ("VALIDATING", "Validating"), ("PROCESSING", "Processing"), ("COMPLETED", "Completed"), ("FAILED", "Failed"), ("PARTIALLY_COMPLETED", "Partially Completed")], default="PENDING", max_length=25)),
                ("celery_task_id", models.CharField(blank=True, default="", max_length=255)),
                ("total_rows", models.PositiveIntegerField(default=0)),
                ("valid_rows", models.PositiveIntegerField(default=0)),
                ("rejected_rows", models.PositiveIntegerField(default=0)),
                ("processing_started_at", models.DateTimeField(blank=True, null=True)),
                ("processing_completed_at", models.DateTimeField(blank=True, null=True)),
                ("error_message", models.TextField(blank=True, default="")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="imports", to="organizations.organization")),
                ("uploaded_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="imports", to=settings.AUTH_USER_MODEL)),
            ],
            options={"db_table": "import_records", "ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="ImportRowError",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("row_number", models.PositiveIntegerField()),
                ("field_name", models.CharField(blank=True, default="", max_length=255)),
                ("error_type", models.CharField(max_length=50)),
                ("error_message", models.TextField()),
                ("raw_value", models.TextField(blank=True, default="")),
                ("import_record", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="row_errors", to="ingestion.importrecord")),
            ],
            options={"db_table": "import_row_errors", "ordering": ["row_number"]},
        ),
        migrations.CreateModel(
            name="CanonicalTransaction",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("source_row_number", models.PositiveIntegerField()),
                ("source", models.CharField(choices=[("ERP", "ERP System"), ("BANK", "Bank Statement"), ("ACCOUNTING", "Accounting System"), ("OTHER", "Other")], max_length=20)),
                ("raw_data", models.JSONField(default=dict)),
                ("external_id", models.CharField(blank=True, default="", max_length=255)),
                ("transaction_date", models.DateField(db_index=True)),
                ("amount", models.DecimalField(decimal_places=6, max_digits=24)),
                ("currency", models.CharField(blank=True, default="", max_length=3)),
                ("reference", models.CharField(blank=True, default="", max_length=512)),
                ("normalized_reference", models.CharField(blank=True, db_index=True, default="", max_length=512)),
                ("description", models.TextField(blank=True, default="")),
                ("counterparty", models.CharField(blank=True, default="", max_length=512)),
                ("normalized_counterparty", models.CharField(blank=True, db_index=True, default="", max_length=512)),
                ("import_record", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="canonical_transactions", to="ingestion.importrecord")),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="canonical_transactions", to="organizations.organization")),
            ],
            options={"db_table": "canonical_transactions", "ordering": ["transaction_date", "source_row_number"]},
        ),
        migrations.AddConstraint(
            model_name="canonicaltransaction",
            constraint=models.UniqueConstraint(fields=("import_record", "source_row_number"), name="unique_import_source_row"),
        ),
    ]
