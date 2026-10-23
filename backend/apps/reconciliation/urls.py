from django.urls import path

from . import views

app_name = "reconciliation"

urlpatterns = [
    path("runs/", views.ReconciliationRunListCreateView.as_view(), name="run-list-create"),
    path("runs/<uuid:run_id>/", views.ReconciliationRunDetailView.as_view(), name="run-detail"),
    path("runs/<uuid:run_id>/results/", views.ReconciliationResultListView.as_view(), name="result-list"),
    path("runs/<uuid:run_id>/candidates/", views.CandidateListView.as_view(), name="candidate-list"),
    path("runs/<uuid:run_id>/candidates/<uuid:candidate_id>/", views.CandidateDetailView.as_view(), name="candidate-detail"),
    path("runs/<uuid:run_id>/transactions/<uuid:transaction_reconciliation_id>/", views.TransactionReconciliationDetailView.as_view(), name="transaction-detail"),
    path("runs/<uuid:run_id>/transactions/<uuid:transaction_reconciliation_id>/confirm/", views.ConfirmCandidateView.as_view(), name="confirm-candidate"),
    path("runs/<uuid:run_id>/transactions/<uuid:transaction_reconciliation_id>/reject/", views.RejectCandidateView.as_view(), name="reject-candidate"),
    path("runs/<uuid:run_id>/transactions/<uuid:transaction_reconciliation_id>/exception/", views.MarkExceptionView.as_view(), name="mark-exception"),
    path("runs/<uuid:run_id>/transactions/<uuid:transaction_reconciliation_id>/resolve/", views.ResolveExceptionView.as_view(), name="resolve-exception"),
    path("runs/<uuid:run_id>/transactions/<uuid:transaction_reconciliation_id>/notes/", views.InvestigationNoteCreateView.as_view(), name="note-create"),
]
