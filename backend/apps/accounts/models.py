"""
Custom User model for FinAudit.
"""

import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """
    Custom user model with UUID primary key.
    
    Extends Django's AbstractUser to provide:
    - UUID primary key (non-guessable)
    - Timestamps
    - Future extensibility
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)

    # Use email as the login identifier
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta:
        db_table = "users"
        ordering = ["-date_joined"]

    def __str__(self):
        return self.email
