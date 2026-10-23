"""
RBAC permissions — enforce role-based access and tenant isolation at the DRF layer.

Usage in views:
    permission_classes = [IsAuthenticated, IsMemberOfOrganization]
    # or for specific roles:
    permission_classes = [IsAuthenticated, IsOrgAdmin]
"""

from rest_framework.permissions import BasePermission

from .models import Membership, MembershipRole


def _get_membership(request, view):
    """
    Resolve the membership for the current request.
    Looks for org_id in URL kwargs or request data.
    """
    org_id = (
        view.kwargs.get("org_id")
        or request.data.get("organization")
        or request.query_params.get("organization")
    )
    if not org_id:
        return None

    try:
        return Membership.objects.select_related("organization").get(
            user=request.user,
            organization_id=org_id,
            is_active=True,
            organization__is_active=True,
        )
    except (Membership.DoesNotExist, ValueError):
        return None


class IsMemberOfOrganization(BasePermission):
    """User must be an active member of the target organization."""

    message = "You are not a member of this organization."

    def has_permission(self, request, view):
        membership = _get_membership(request, view)
        if membership:
            request.membership = membership
            request.organization = membership.organization
            return True
        return False


class IsOrgAdmin(BasePermission):
    """User must be an ADMIN of the target organization."""

    message = "Admin role required."

    def has_permission(self, request, view):
        membership = _get_membership(request, view)
        if membership and membership.role == MembershipRole.ADMIN:
            request.membership = membership
            request.organization = membership.organization
            return True
        return False


class IsOrgAdminOrManager(BasePermission):
    """User must be ADMIN or FINANCE_MANAGER."""

    message = "Admin or Finance Manager role required."

    def has_permission(self, request, view):
        membership = _get_membership(request, view)
        if membership and membership.role in (
            MembershipRole.ADMIN,
            MembershipRole.FINANCE_MANAGER,
        ):
            request.membership = membership
            request.organization = membership.organization
            return True
        return False


class HasOrgRole(BasePermission):
    """
    Configurable role check. Set `required_roles` on the view:

        class MyView(APIView):
            required_roles = [MembershipRole.ADMIN, MembershipRole.AUDITOR]
            permission_classes = [IsAuthenticated, HasOrgRole]
    """

    message = "Insufficient role for this action."

    def has_permission(self, request, view):
        required_roles = getattr(view, "required_roles", [])
        membership = _get_membership(request, view)
        if membership and membership.role in required_roles:
            request.membership = membership
            request.organization = membership.organization
            return True
        return False
