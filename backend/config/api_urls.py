"""
API v1 URL Configuration.

Each Django app registers its own routes here.
"""

from django.urls import include, path

from apps.organizations.ai_views import AssistantView

urlpatterns = [
    path("auth/", include("apps.accounts.urls", namespace="accounts")),
    path("organizations/", include("apps.organizations.urls", namespace="organizations")),
    path(
        "organizations/<uuid:org_id>/ai/assist/",
        AssistantView.as_view(),
        name="ai-assist",
    ),
    path(
        "organizations/<uuid:org_id>/imports/",
        include("apps.ingestion.urls", namespace="ingestion"),
    ),
    path(
        "organizations/<uuid:org_id>/reconciliation/",
        include("apps.reconciliation.urls", namespace="reconciliation"),
    ),
]
