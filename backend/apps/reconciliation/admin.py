from django.contrib import admin

from .models import (
    MatchCandidate,
    ReconciliationInvestigationNote,
    ReconciliationRun,
    TransactionReconciliation,
)


@admin.register(ReconciliationRun)
class ReconciliationRunAdmin(admin.ModelAdmin):
    list_display = (
        "id", "organization", "status", "total_source", "total_target",
        "matched_count", "unmatched_count", "conflict_count", "created_at",
    )
    list_filter = ("status",)
    readonly_fields = ("config",)


@admin.register(TransactionReconciliation)
class TransactionReconciliationAdmin(admin.ModelAdmin):
    list_display = ("transaction", "run", "side", "state")
    list_filter = ("state", "side")


@admin.register(MatchCandidate)
class MatchCandidateAdmin(admin.ModelAdmin):
    list_display = (
        "source_transaction", "target_transaction", "score", "is_selected",
    )
    list_filter = ("is_selected",)
    readonly_fields = ("evidence",)


@admin.register(ReconciliationInvestigationNote)
class ReconciliationInvestigationNoteAdmin(admin.ModelAdmin):
    list_display = ("transaction_reconciliation", "author", "created_at")
    search_fields = ("content", "author__email")
