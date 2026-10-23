"""
Ingestion URL routes.
"""

from django.urls import path

from . import views

app_name = "ingestion"

urlpatterns = [
    path("upload/", views.FileUploadView.as_view(), name="file-upload"),
    path("", views.ImportListView.as_view(), name="import-list"),
    path("<uuid:import_id>/", views.ImportDetailView.as_view(), name="import-detail"),
    path("<uuid:import_id>/errors/", views.ImportErrorsView.as_view(), name="import-errors"),
]
