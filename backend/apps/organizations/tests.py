"""
Tests for the organizations app — CRUD, membership, RBAC, tenant isolation.
"""

import pytest
from rest_framework import status

from apps.organizations.models import Membership, MembershipRole, Organization

pytestmark = pytest.mark.django_db


class TestOrganizationCRUD:
    def test_create_organization(self, authenticated_client):
        response = authenticated_client.post("/api/v1/organizations/", {
            "name": "New Org",
            "slug": "new-org",
        })
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["name"] == "New Org"

    def test_creator_becomes_admin(self, authenticated_client, user):
        response = authenticated_client.post("/api/v1/organizations/", {
            "name": "New Org",
            "slug": "new-org-admin",
        })
        org_id = response.data["id"]
        membership = Membership.objects.get(user=user, organization_id=org_id)
        assert membership.role == MembershipRole.ADMIN

    def test_list_organizations_only_own(self, authenticated_client, user,
                                          organization, other_organization,
                                          create_membership, other_user):
        # User is member of organization but NOT other_organization
        create_membership(user, organization, MembershipRole.ADMIN)
        create_membership(other_user, other_organization, MembershipRole.ADMIN)

        response = authenticated_client.get("/api/v1/organizations/")
        assert response.status_code == status.HTTP_200_OK
        org_ids = [o["id"] for o in response.data["results"]]
        assert str(organization.id) in org_ids
        assert str(other_organization.id) not in org_ids

    def test_retrieve_organization_member(self, admin_client, organization):
        response = admin_client.get(f"/api/v1/organizations/{organization.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["name"] == organization.name

    def test_retrieve_organization_non_member_denied(self, authenticated_client,
                                                      other_organization):
        response = authenticated_client.get(
            f"/api/v1/organizations/{other_organization.id}/"
        )
        assert response.status_code in (
            status.HTTP_403_FORBIDDEN,
            status.HTTP_404_NOT_FOUND,
        )

    def test_update_organization_admin(self, admin_client, organization):
        response = admin_client.patch(
            f"/api/v1/organizations/{organization.id}/",
            {"name": "Updated Org"},
        )
        assert response.status_code == status.HTTP_200_OK
        organization.refresh_from_db()
        assert organization.name == "Updated Org"

    def test_update_organization_non_admin_denied(self, analyst_client, organization):
        response = analyst_client.patch(
            f"/api/v1/organizations/{organization.id}/",
            {"name": "Hacked Org"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN


class TestMembership:
    def test_list_members(self, admin_client, organization):
        response = admin_client.get(
            f"/api/v1/organizations/{organization.id}/members/"
        )
        assert response.status_code == status.HTTP_200_OK

    def test_add_member_admin_only(self, admin_client, organization, other_user):
        response = admin_client.post(
            f"/api/v1/organizations/{organization.id}/members/",
            {"email": other_user.email, "role": MembershipRole.AUDITOR},
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert Membership.objects.filter(
            user=other_user, organization=organization
        ).exists()

    def test_add_member_analyst_denied(self, analyst_client, organization, other_user):
        response = analyst_client.post(
            f"/api/v1/organizations/{organization.id}/members/",
            {"email": other_user.email, "role": MembershipRole.AUDITOR},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_add_duplicate_member(self, admin_client, organization, user):
        # user is already a member via admin_membership fixture
        response = admin_client.post(
            f"/api/v1/organizations/{organization.id}/members/",
            {"email": user.email, "role": MembershipRole.AUDITOR},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestTenantIsolation:
    """Verify users cannot access other organizations' data."""

    def test_user_cannot_list_other_org_members(self, authenticated_client,
                                                  other_organization, other_user,
                                                  create_membership):
        create_membership(other_user, other_organization, MembershipRole.ADMIN)
        response = authenticated_client.get(
            f"/api/v1/organizations/{other_organization.id}/members/"
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_user_cannot_add_member_to_other_org(self, authenticated_client,
                                                   other_organization, other_user,
                                                   create_membership):
        create_membership(other_user, other_organization, MembershipRole.ADMIN)
        response = authenticated_client.post(
            f"/api/v1/organizations/{other_organization.id}/members/",
            {"email": "someone@example.com", "role": MembershipRole.AUDITOR},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_organization_model_has_uuid_pk(self, organization):
        import uuid
        assert isinstance(organization.id, uuid.UUID)

    def test_membership_unique_constraint(self, user, organization, create_membership):
        create_membership(user, organization, MembershipRole.ADMIN)
        with pytest.raises(Exception):  # IntegrityError
            create_membership(user, organization, MembershipRole.AUDITOR)
