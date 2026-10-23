"""
Base models providing shared fields across all FinAudit models.
"""

import uuid

from django.db import models


class TimestampedModel(models.Model):
    """Abstract base model with created/updated timestamps."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ["-created_at"]


class UUIDModel(models.Model):
    """Abstract base model using UUID primary keys."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class BaseModel(UUIDModel, TimestampedModel):
    """Standard base model combining UUID primary key and timestamps."""

    class Meta:
        abstract = True
        ordering = ["-created_at"]
