"""Tenant-scoped REST API for reconciliation runs and review workflows."""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.organizations.models import MembershipRole
from apps.organizations.permissions import HasOrgRole, IsMemberOfOrganization

from .models import MatchCandidate, ReconciliationRun, TransactionReconciliation
from .serializers import (
    CandidateActionSerializer,
    ConfirmCandidateSerializer,
    ExceptionActionSerializer,
    InvestigationNoteCreateSerializer,
    InvestigationNoteSerializer,
    MatchCandidateSerializer,
    ReconciliationRunCreateSerializer,
    ReconciliationRunSerializer,
    ResolveExceptionSerializer,
    TransactionReconciliationDetailSerializer,
    TransactionReconciliationSerializer,
)
from .services import (
    add_investigation_note,
    confirm_candidate,
    create_and_start_run,
    mark_exception,
    reject_candidate,
    resolve_exception,
)


REVIEW_ROLES = [
    MembershipRole.ADMIN,
    MembershipRole.FINANCE_MANAGER,
    MembershipRole.RECONCILIATION_ANALYST,
]
RUN_ROLES = [MembershipRole.ADMIN, MembershipRole.FINANCE_MANAGER]


class OrganizationRunMixin:
    permission_classes = [permissions.IsAuthenticated, IsMemberOfOrganization]

    def get_run(self):
        return get_object_or_404(
            ReconciliationRun.objects.select_related("source_import", "target_import", "initiated_by"),
            pk=self.kwargs["run_id"],
            organization=self.request.organization,
        )


class ReconciliationRunListCreateView(OrganizationRunMixin, generics.ListCreateAPIView):
    serializer_class = ReconciliationRunSerializer

    def get_permissions(self):
        if self.request.method == "POST":
            self.required_roles = RUN_ROLES
            return [permissions.IsAuthenticated(), HasOrgRole()]
        return [permissions.IsAuthenticated(), IsMemberOfOrganization()]

    def get_queryset(self):
        return ReconciliationRun.objects.filter(
            organization=self.request.organization
        ).select_related("source_import", "target_import", "initiated_by")

    def create(self, request, *args, **kwargs):
        serializer = ReconciliationRunCreateSerializer(
            data=request.data,
            context={"organization": request.organization},
        )
        serializer.is_valid(raise_exception=True)
        try:
            run = create_and_start_run(
                organization=request.organization,
                initiated_by=request.user,
                source_import=serializer.validated_data["source_import_record"],
                target_import=serializer.validated_data["target_import_record"],
            )
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"detail": exc.messages})
        return Response(ReconciliationRunSerializer(run).data, status=status.HTTP_201_CREATED)


class ReconciliationRunDetailView(OrganizationRunMixin, APIView):
    def get(self, request, org_id, run_id):
        return Response(ReconciliationRunSerializer(self.get_run()).data)


class ReconciliationResultListView(OrganizationRunMixin, generics.ListAPIView):
    serializer_class = TransactionReconciliationSerializer

    def get_queryset(self):
        run = self.get_run()
        return TransactionReconciliation.objects.filter(run=run).select_related("transaction", "run")


class TransactionReconciliationDetailView(OrganizationRunMixin, APIView):
    def get_transaction_reconciliation(self):
        return get_object_or_404(
            TransactionReconciliation.objects.select_related("transaction", "run").prefetch_related(
                "investigation_notes__author"
            ),
            pk=self.kwargs["transaction_reconciliation_id"],
            run=self.get_run(),
        )

    def get(self, request, org_id, run_id, transaction_reconciliation_id):
        return Response(
            TransactionReconciliationDetailSerializer(
                self.get_transaction_reconciliation()
            ).data
        )


class CandidateListView(OrganizationRunMixin, generics.ListAPIView):
    serializer_class = MatchCandidateSerializer

    def get_queryset(self):
        return MatchCandidate.objects.filter(run=self.get_run()).select_related(
            "source_transaction", "target_transaction", "reviewed_by"
        )


class CandidateDetailView(OrganizationRunMixin, APIView):
    def get(self, request, org_id, run_id, candidate_id):
        candidate = get_object_or_404(
            MatchCandidate.objects.select_related(
                "source_transaction", "target_transaction", "reviewed_by"
            ),
            pk=candidate_id,
            run=self.get_run(),
        )
        return Response(MatchCandidateSerializer(candidate).data)


class WorkflowActionMixin(OrganizationRunMixin):
    def get_permissions(self):
        self.required_roles = REVIEW_ROLES
        return [permissions.IsAuthenticated(), HasOrgRole()]

    def get_transaction_reconciliation(self):
        return get_object_or_404(
            TransactionReconciliation.objects.select_related("transaction", "run"),
            pk=self.kwargs["transaction_reconciliation_id"],
            run=self.get_run(),
        )

    def validation_error(self, exc):
        raise serializers.ValidationError({"detail": exc.messages})


class ConfirmCandidateView(WorkflowActionMixin, APIView):
    def post(self, request, org_id, run_id, transaction_reconciliation_id):
        state = self.get_transaction_reconciliation()
        serializer = ConfirmCandidateSerializer(
            data=request.data,
            context={"transaction_reconciliation": state},
        )
        serializer.is_valid(raise_exception=True)
        try:
            confirm_candidate(
                transaction_reconciliation=state,
                candidate=serializer.context["candidate"],
                user=request.user,
                note=serializer.validated_data.get("note", ""),
            )
        except DjangoValidationError as exc:
            self.validation_error(exc)
        return Response(TransactionReconciliationDetailSerializer(state).data)


class RejectCandidateView(WorkflowActionMixin, APIView):
    def post(self, request, org_id, run_id, transaction_reconciliation_id):
        state = self.get_transaction_reconciliation()
        serializer = CandidateActionSerializer(
            data=request.data,
            context={"transaction_reconciliation": state},
        )
        serializer.is_valid(raise_exception=True)
        try:
            reject_candidate(
                transaction_reconciliation=state,
                candidate=serializer.context["candidate"],
                user=request.user,
                note=serializer.validated_data.get("note", ""),
            )
        except DjangoValidationError as exc:
            self.validation_error(exc)
        return Response(TransactionReconciliationDetailSerializer(state).data)


class MarkExceptionView(WorkflowActionMixin, APIView):
    def post(self, request, org_id, run_id, transaction_reconciliation_id):
        state = self.get_transaction_reconciliation()
        serializer = ExceptionActionSerializer(
            data=request.data,
            context={"transaction_reconciliation": state},
        )
        serializer.is_valid(raise_exception=True)
        try:
            mark_exception(
                transaction_reconciliation=state,
                user=request.user,
                note=serializer.validated_data.get("note", ""),
            )
        except DjangoValidationError as exc:
            self.validation_error(exc)
        return Response(TransactionReconciliationDetailSerializer(state).data)


class ResolveExceptionView(WorkflowActionMixin, APIView):
    def post(self, request, org_id, run_id, transaction_reconciliation_id):
        state = self.get_transaction_reconciliation()
        serializer = ResolveExceptionSerializer(
            data=request.data,
            context={"transaction_reconciliation": state},
        )
        serializer.is_valid(raise_exception=True)
        try:
            resolve_exception(
                transaction_reconciliation=state,
                user=request.user,
                note=serializer.validated_data.get("note", ""),
            )
        except DjangoValidationError as exc:
            self.validation_error(exc)
        return Response(TransactionReconciliationDetailSerializer(state).data)


class InvestigationNoteCreateView(WorkflowActionMixin, APIView):
    def post(self, request, org_id, run_id, transaction_reconciliation_id):
        state = self.get_transaction_reconciliation()
        serializer = InvestigationNoteCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        note = add_investigation_note(
            transaction_reconciliation=state,
            user=request.user,
            content=serializer.validated_data["content"],
        )
        return Response(InvestigationNoteSerializer(note).data, status=status.HTTP_201_CREATED)
