"""
Organization URL routes.
"""

from django.urls import path

from . import views

app_name = "organizations"

urlpatterns = [
    path("", views.OrganizationListCreateView.as_view(), name="org-list-create"),
    path("<uuid:org_id>/", views.OrganizationDetailView.as_view(), name="org-detail"),
    path("<uuid:org_id>/members/", views.MembershipListCreateView.as_view(), name="member-list-create"),
    path("<uuid:org_id>/members/<uuid:membership_id>/", views.MembershipDetailView.as_view(), name="member-detail"),
]
