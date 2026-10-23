"""
Organization and Membership models — multi-tenancy and RBAC foundation.
"""

from django.conf import settings
from django.db import models

from apps.common.models import BaseModel


class Organization(BaseModel):
    """
    Tenant entity — all domain data is scoped to an organization.
    """

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "organizations"
        ordering = ["name"]

    def __str__(self):
        return self.name


class MembershipRole(models.TextChoices):
    ADMIN = "ADMIN", "Admin"
    FINANCE_MANAGER = "FINANCE_MANAGER", "Finance Manager"
    RECONCILIATION_ANALYST = "RECONCILIATION_ANALYST", "Reconciliation Analyst"
    AUDITOR = "AUDITOR", "Auditor"


class Membership(BaseModel):
    """
    Links a user to an organization with a specific role.

    A user may belong to multiple organizations, each with an independent role.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="memberships",
    )
    role = models.CharField(
        max_length=30,
        choices=MembershipRole.choices,
        default=MembershipRole.RECONCILIATION_ANALYST,
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "memberships"
        unique_together = ("user", "organization")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.email} → {self.organization.name} ({self.role})"
