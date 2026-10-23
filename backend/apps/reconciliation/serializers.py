"""DRF serializers for reconciliation execution and review workflows."""

from rest_framework import serializers

from apps.ingestion.models import CanonicalTransaction, ImportRecord

from .models import (
    MatchCandidate,
    ReconciliationInvestigationNote,
    ReconciliationRun,
    TransactionReconciliation,
    TransactionState,
)


class CanonicalTransactionSummarySerializer(serializers.ModelSerializer):
    amount = serializers.DecimalField(max_digits=24, decimal_places=6, coerce_to_string=True)

    class Meta:
        model = CanonicalTransaction
        fields = (
            "id", "external_id", "transaction_date", "amount", "currency",
            "reference", "description", "counterparty", "source",
            "source_row_number",
        )


class ReconciliationRunSerializer(serializers.ModelSerializer):
    initiated_by_email = serializers.EmailField(source="initiated_by.email", read_only=True)

    class Meta:
        model = ReconciliationRun
        fields = (
            "id", "organization", "initiated_by", "initiated_by_email",
            "source_import", "target_import", "status", "config",
            "total_source", "total_target", "matched_count", "unmatched_count",
            "conflict_count", "exception_count", "started_at", "completed_at",
            "error_message", "created_at", "updated_at",
        )
        read_only_fields = fields


class ReconciliationRunCreateSerializer(serializers.Serializer):
    source_import = serializers.UUIDField()
    target_import = serializers.UUIDField()

    def validate(self, attrs):
        if attrs["source_import"] == attrs["target_import"]:
            raise serializers.ValidationError(
                {"target_import": "Source and target imports must be different."}
            )
        organization = self.context["organization"]
        imports = {
            import_record.id: import_record
            for import_record in ImportRecord.objects.filter(
                organization=organization,
                id__in=[attrs["source_import"], attrs["target_import"]],
            )
        }
        if attrs["source_import"] not in imports:
            raise serializers.ValidationError({"source_import": "Import was not found."})
        if attrs["target_import"] not in imports:
            raise serializers.ValidationError({"target_import": "Import was not found."})
        attrs["source_import_record"] = imports[attrs["source_import"]]
        attrs["target_import_record"] = imports[attrs["target_import"]]
        return attrs


class InvestigationNoteSerializer(serializers.ModelSerializer):
    author_email = serializers.EmailField(source="author.email", read_only=True)

    class Meta:
        model = ReconciliationInvestigationNote
        fields = ("id", "author", "author_email", "content", "created_at")
        read_only_fields = ("id", "author", "author_email", "created_at")


class MatchCandidateSerializer(serializers.ModelSerializer):
    score = serializers.DecimalField(max_digits=5, decimal_places=4, coerce_to_string=True)
    reference_score = serializers.DecimalField(max_digits=5, decimal_places=4, coerce_to_string=True)
    amount_score = serializers.DecimalField(max_digits=5, decimal_places=4, coerce_to_string=True)
    date_score = serializers.DecimalField(max_digits=5, decimal_places=4, coerce_to_string=True)
    counterparty_score = serializers.DecimalField(max_digits=5, decimal_places=4, coerce_to_string=True)
    source_transaction = CanonicalTransactionSummarySerializer(read_only=True)
    target_transaction = CanonicalTransactionSummarySerializer(read_only=True)
    reviewed_by_email = serializers.EmailField(source="reviewed_by.email", read_only=True)

    class Meta:
        model = MatchCandidate
        fields = (
            "id", "score", "reference_score", "amount_score", "date_score",
            "counterparty_score", "evidence", "is_selected", "review_status",
            "reviewed_by", "reviewed_by_email", "reviewed_at", "source_transaction",
            "target_transaction", "created_at",
        )
        read_only_fields = fields


class TransactionReconciliationSerializer(serializers.ModelSerializer):
    transaction = CanonicalTransactionSummarySerializer(read_only=True)
    candidate_count = serializers.SerializerMethodField()

    class Meta:
        model = TransactionReconciliation
        fields = ("id", "transaction", "side", "state", "candidate_count", "created_at", "updated_at")
        read_only_fields = fields

    def get_candidate_count(self, obj):
        if obj.side == "SOURCE":
            return obj.run.candidates.filter(source_transaction_id=obj.transaction_id).count()
        return obj.run.candidates.filter(target_transaction_id=obj.transaction_id).count()


class TransactionReconciliationDetailSerializer(TransactionReconciliationSerializer):
    candidates = serializers.SerializerMethodField()
    investigation_notes = InvestigationNoteSerializer(many=True, read_only=True)

    class Meta(TransactionReconciliationSerializer.Meta):
        fields = TransactionReconciliationSerializer.Meta.fields + ("candidates", "investigation_notes")

    def get_candidates(self, obj):
        if obj.side == "SOURCE":
            candidates = obj.run.candidates.filter(source_transaction_id=obj.transaction_id)
        else:
            candidates = obj.run.candidates.filter(target_transaction_id=obj.transaction_id)
        return MatchCandidateSerializer(candidates, many=True).data


class CandidateActionSerializer(serializers.Serializer):
    candidate_id = serializers.UUIDField()
    note = serializers.CharField(required=False, allow_blank=False, max_length=4000)

    def validate_candidate_id(self, value):
        transaction_reconciliation = self.context["transaction_reconciliation"]
        if transaction_reconciliation.side != "SOURCE":
            raise serializers.ValidationError("Candidates can only be reviewed from a source transaction.")
        try:
            candidate = MatchCandidate.objects.get(
                id=value,
                run=transaction_reconciliation.run,
                source_transaction_id=transaction_reconciliation.transaction_id,
            )
        except MatchCandidate.DoesNotExist:
            raise serializers.ValidationError("Candidate was not found for this transaction.")
        self.context["candidate"] = candidate
        return value


class ConfirmCandidateSerializer(CandidateActionSerializer):
    def validate(self, attrs):
        transaction_reconciliation = self.context["transaction_reconciliation"]
        if (
            transaction_reconciliation.state != TransactionState.MATCHED
            and not transaction_reconciliation.can_transition_to(TransactionState.MATCHED)
        ):
            raise serializers.ValidationError("This transaction cannot be confirmed from its current state.")
        return attrs


class ExceptionActionSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=False, max_length=4000)

    def validate(self, attrs):
        transaction_reconciliation = self.context["transaction_reconciliation"]
        if not transaction_reconciliation.can_transition_to(TransactionState.EXCEPTION):
            raise serializers.ValidationError("This transaction cannot be marked as an exception.")
        return attrs


class ResolveExceptionSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=False, max_length=4000)

    def validate(self, attrs):
        state = self.context["transaction_reconciliation"].state
        if state not in (TransactionState.EXCEPTION, TransactionState.UNDER_REVIEW):
            raise serializers.ValidationError("Only an exception can be resolved.")
        return attrs


class InvestigationNoteCreateSerializer(serializers.Serializer):
    content = serializers.CharField(allow_blank=False, max_length=4000)
