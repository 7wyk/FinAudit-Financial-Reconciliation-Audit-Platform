import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("ingestion", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReconciliationRun",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("status", models.CharField(choices=[("PENDING", "Pending"), ("RUNNING", "Running"), ("COMPLETED", "Completed"), ("FAILED", "Failed")], default="PENDING", max_length=20)),
                ("config", models.JSONField(default=dict, help_text="Matching parameters used for this run")),
                ("total_source", models.PositiveIntegerField(default=0)),
                ("total_target", models.PositiveIntegerField(default=0)),
                ("matched_count", models.PositiveIntegerField(default=0)),
                ("unmatched_count", models.PositiveIntegerField(default=0)),
                ("conflict_count", models.PositiveIntegerField(default=0)),
                ("exception_count", models.PositiveIntegerField(default=0)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("error_message", models.TextField(blank=True, default="")),
                ("initiated_by", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reconciliation_runs", to=settings.AUTH_USER_MODEL)),
                ("organization", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reconciliation_runs", to="organizations.organization")),
                ("source_import", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="source_runs", to="ingestion.importrecord")),
                ("target_import", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="target_runs", to="ingestion.importrecord")),
            ],
            options={"db_table": "reconciliation_runs", "ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="TransactionReconciliation",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("side", models.CharField(choices=[("SOURCE", "Source"), ("TARGET", "Target")], max_length=10)),
                ("state", models.CharField(choices=[("UNMATCHED", "Unmatched"), ("CANDIDATE", "Has candidates"), ("MATCHED", "Matched"), ("PARTIALLY_MATCHED", "Partially matched"), ("CONFLICT", "Conflicting candidates"), ("EXCEPTION", "Exception"), ("UNDER_REVIEW", "Under review"), ("RESOLVED", "Resolved"), ("REJECTED", "Rejected")], default="UNMATCHED", max_length=25)),
                ("run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="transaction_states", to="reconciliation.reconciliationrun")),
                ("transaction", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reconciliation_states", to="ingestion.canonicaltransaction")),
            ],
            options={"db_table": "transaction_reconciliations"},
        ),
        migrations.CreateModel(
            name="MatchCandidate",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("score", models.DecimalField(decimal_places=4, max_digits=5)),
                ("reference_score", models.DecimalField(decimal_places=4, default=0, max_digits=5)),
                ("amount_score", models.DecimalField(decimal_places=4, default=0, max_digits=5)),
                ("date_score", models.DecimalField(decimal_places=4, default=0, max_digits=5)),
                ("counterparty_score", models.DecimalField(decimal_places=4, default=0, max_digits=5)),
                ("evidence", models.JSONField(default=dict, help_text="Structured explanation metadata")),
                ("is_selected", models.BooleanField(default=False)),
                ("review_status", models.CharField(choices=[("PENDING", "Pending"), ("CONFIRMED", "Confirmed"), ("REJECTED", "Rejected")], default="PENDING", max_length=20)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("reviewed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reviewed_match_candidates", to=settings.AUTH_USER_MODEL)),
                ("run", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="candidates", to="reconciliation.reconciliationrun")),
                ("source_transaction", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="source_candidates", to="ingestion.canonicaltransaction")),
                ("target_transaction", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="target_candidates", to="ingestion.canonicaltransaction")),
            ],
            options={"db_table": "match_candidates", "ordering": ["-score"]},
        ),
        migrations.CreateModel(
            name="ReconciliationInvestigationNote",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("content", models.TextField()),
                ("author", models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="reconciliation_investigation_notes", to=settings.AUTH_USER_MODEL)),
                ("transaction_reconciliation", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="investigation_notes", to="reconciliation.transactionreconciliation")),
            ],
            options={"db_table": "reconciliation_investigation_notes", "ordering": ["created_at"]},
        ),
        migrations.AddConstraint(
            model_name="transactionreconciliation",
            constraint=models.UniqueConstraint(fields=("run", "transaction"), name="unique_run_transaction"),
        ),
        migrations.AddConstraint(
            model_name="matchcandidate",
            constraint=models.UniqueConstraint(fields=("run", "source_transaction", "target_transaction"), name="unique_candidate_pair"),
        ),
    ]
