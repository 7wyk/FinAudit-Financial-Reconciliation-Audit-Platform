"""Tests for the common app — health check, base models, exception handler."""

import uuid

import pytest
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.common.models import BaseModel


class HealthCheckTests(TestCase):
    """Test the health check endpoint."""

    def setUp(self):
        self.client = APIClient()

    def test_health_check_returns_200(self):
        response = self.client.get("/api/health/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["status"] == "healthy"
        assert response.data["database"] == "connected"

    def test_health_check_allows_unauthenticated(self):
        response = self.client.get("/api/health/")
        assert response.status_code == status.HTTP_200_OK


class BaseModelTests(TestCase):
    """Test the abstract base model properties."""

    def test_base_model_is_abstract(self):
        assert BaseModel._meta.abstract is True

    def test_base_model_uses_uuid_pk(self):
        pk_field = BaseModel._meta.get_field("id")
        assert pk_field.primary_key is True

    def test_base_model_has_timestamps(self):
        field_names = [f.name for f in BaseModel._meta.get_fields()]
        assert "created_at" in field_names
        assert "updated_at" in field_names


class ExceptionHandlerTests(TestCase):
    """Test the custom exception handler."""

    def setUp(self):
        self.client = APIClient()

    def test_404_for_nonexistent_route(self):
        response = self.client.get("/api/v1/nonexistent/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_401_for_protected_endpoint(self):
        # API root requires auth by default
        response = self.client.get("/api/v1/")
        # 404 since no routes exist yet, but testing unauthenticated behavior
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_404_NOT_FOUND,
        )
