"""
Organization views — CRUD, membership management.
"""

from rest_framework import generics, permissions, status
from rest_framework.response import Response

from .models import Membership, MembershipRole, Organization
from .permissions import IsOrgAdmin, IsMemberOfOrganization
from .serializers import (
    MembershipCreateSerializer,
    MembershipSerializer,
    OrganizationCreateSerializer,
    OrganizationSerializer,
)


class OrganizationListCreateView(generics.ListCreateAPIView):
    """
    GET  — list organizations the user belongs to.
    POST — create a new organization (user becomes ADMIN).
    """

    def get_serializer_class(self):
        if self.request.method == "POST":
            return OrganizationCreateSerializer
        return OrganizationSerializer

    def get_queryset(self):
        return Organization.objects.filter(
            memberships__user=self.request.user,
            memberships__is_active=True,
            is_active=True,
        ).distinct()


class OrganizationDetailView(generics.RetrieveUpdateAPIView):
    """
    GET  — retrieve org details (members only).
    PATCH — update org (admins only).
    """

    serializer_class = OrganizationSerializer
    lookup_url_kwarg = "org_id"

    def get_permissions(self):
        if self.request.method in ("PUT", "PATCH"):
            return [permissions.IsAuthenticated(), IsOrgAdmin()]
        return [permissions.IsAuthenticated(), IsMemberOfOrganization()]

    def get_queryset(self):
        return Organization.objects.filter(
            memberships__user=self.request.user,
            memberships__is_active=True,
            is_active=True,
        ).distinct()


class MembershipListCreateView(generics.ListCreateAPIView):
    """
    GET  — list members of the organization.
    POST — add a member (admin only).
    """

    def get_serializer_class(self):
        if self.request.method == "POST":
            return MembershipCreateSerializer
        return MembershipSerializer

    def get_permissions(self):
        if self.request.method == "POST":
            return [permissions.IsAuthenticated(), IsOrgAdmin()]
        return [permissions.IsAuthenticated(), IsMemberOfOrganization()]

    def get_queryset(self):
        org_id = self.kwargs["org_id"]
        return Membership.objects.filter(
            organization_id=org_id,
            organization__is_active=True,
        ).select_related("user")

    def perform_create(self, serializer):
        org = Organization.objects.get(pk=self.kwargs["org_id"])
        serializer.save(context={"organization": org})

    def create(self, request, *args, **kwargs):
        org = Organization.objects.get(pk=self.kwargs["org_id"])
        serializer = MembershipCreateSerializer(
            data=request.data,
            context={"organization": org, "request": request},
        )
        serializer.is_valid(raise_exception=True)
        membership = serializer.create(serializer.validated_data)
        return Response(
            MembershipSerializer(membership).data,
            status=status.HTTP_201_CREATED,
        )


class MembershipDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    — membership details.
    PATCH  — update role (admin only).
    DELETE — remove member (admin only).
    """

    serializer_class = MembershipSerializer
    lookup_url_kwarg = "membership_id"

    def get_permissions(self):
        if self.request.method in ("PUT", "PATCH", "DELETE"):
            return [permissions.IsAuthenticated(), IsOrgAdmin()]
        return [permissions.IsAuthenticated(), IsMemberOfOrganization()]

    def get_queryset(self):
        return Membership.objects.filter(
            organization_id=self.kwargs["org_id"],
        ).select_related("user", "organization")
