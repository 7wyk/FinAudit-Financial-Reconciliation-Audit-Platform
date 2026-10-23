"""
Shared pytest fixtures and factories for the FinAudit test suite.
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.organizations.models import Membership, MembershipRole, Organization

User = get_user_model()


@pytest.fixture
def api_client():
    """Unauthenticated DRF API test client."""
    return APIClient()


@pytest.fixture
def create_user(db):
    """Factory fixture to create users."""
    def _create_user(email="test@example.com", password="TestPass123!", **kwargs):
        kwargs.setdefault("username", email.split("@")[0])
        return User.objects.create_user(email=email, password=password, **kwargs)
    return _create_user


@pytest.fixture
def user(create_user):
    """A default test user."""
    return create_user()


@pytest.fixture
def other_user(create_user):
    """A second test user for isolation tests."""
    return create_user(email="other@example.com", username="other")


@pytest.fixture
def create_organization(db):
    """Factory fixture to create organizations."""
    _counter = [0]

    def _create_org(name="Test Org", slug=None, **kwargs):
        _counter[0] += 1
        if slug is None:
            slug = f"test-org-{_counter[0]}"
        return Organization.objects.create(name=name, slug=slug, **kwargs)
    return _create_org


@pytest.fixture
def organization(create_organization):
    """A default test organization."""
    return create_organization(name="Test Organization", slug="test-org")


@pytest.fixture
def other_organization(create_organization):
    """A second organization for tenant isolation tests."""
    return create_organization(name="Other Organization", slug="other-org")


@pytest.fixture
def create_membership(db):
    """Factory fixture to create memberships."""
    def _create_membership(user, organization, role=MembershipRole.ADMIN):
        return Membership.objects.create(
            user=user, organization=organization, role=role,
        )
    return _create_membership


@pytest.fixture
def admin_membership(user, organization, create_membership):
    """User as ADMIN of the default organization."""
    return create_membership(user, organization, MembershipRole.ADMIN)


@pytest.fixture
def analyst_membership(user, organization, create_membership):
    """User as RECONCILIATION_ANALYST of the default organization."""
    return create_membership(user, organization, MembershipRole.RECONCILIATION_ANALYST)


@pytest.fixture
def authenticated_client(api_client, user):
    """API client authenticated as the default user."""
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def admin_client(api_client, user, admin_membership):
    """API client authenticated as an org admin."""
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def analyst_client(api_client, user, analyst_membership):
    """API client authenticated as a reconciliation analyst."""
    api_client.force_authenticate(user=user)
    return api_client
