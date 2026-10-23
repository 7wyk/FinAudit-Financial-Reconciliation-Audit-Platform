"""
Tests for the accounts app — registration, authentication, profile, password.
"""

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

User = get_user_model()

pytestmark = pytest.mark.django_db


class TestRegistration:
    def test_register_success(self, api_client):
        response = api_client.post("/api/v1/auth/register/", {
            "email": "new@example.com",
            "username": "newuser",
            "password": "StrongPass123!",
            "password_confirm": "StrongPass123!",
        })
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["email"] == "new@example.com"
        assert "password" not in response.data

    def test_register_password_mismatch(self, api_client):
        response = api_client.post("/api/v1/auth/register/", {
            "email": "new@example.com",
            "username": "newuser",
            "password": "StrongPass123!",
            "password_confirm": "DifferentPass456!",
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_register_weak_password(self, api_client):
        response = api_client.post("/api/v1/auth/register/", {
            "email": "new@example.com",
            "username": "newuser",
            "password": "123",
            "password_confirm": "123",
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_register_duplicate_email(self, api_client, user):
        response = api_client.post("/api/v1/auth/register/", {
            "email": user.email,
            "username": "anotheruser",
            "password": "StrongPass123!",
            "password_confirm": "StrongPass123!",
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestJWTAuth:
    def test_login_success(self, api_client, user):
        response = api_client.post("/api/v1/auth/token/", {
            "email": user.email,
            "password": "TestPass123!",
        })
        assert response.status_code == status.HTTP_200_OK
        assert "access" in response.data
        assert "refresh" in response.data

    def test_login_wrong_password(self, api_client, user):
        response = api_client.post("/api/v1/auth/token/", {
            "email": user.email,
            "password": "WrongPass!",
        })
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_token_refresh(self, api_client, user):
        login = api_client.post("/api/v1/auth/token/", {
            "email": user.email,
            "password": "TestPass123!",
        })
        refresh_token = login.data["refresh"]

        response = api_client.post("/api/v1/auth/token/refresh/", {
            "refresh": refresh_token,
        })
        assert response.status_code == status.HTTP_200_OK
        assert "access" in response.data

    def test_access_protected_endpoint_without_token(self, api_client):
        response = api_client.get("/api/v1/auth/profile/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestProfile:
    def test_get_profile(self, authenticated_client, user):
        response = authenticated_client.get("/api/v1/auth/profile/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["email"] == user.email

    def test_profile_requires_auth(self, api_client):
        response = api_client.get("/api/v1/auth/profile/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestPasswordChange:
    def test_change_password_success(self, authenticated_client, user):
        response = authenticated_client.post("/api/v1/auth/password/change/", {
            "old_password": "TestPass123!",
            "new_password": "NewStrongPass456!",
        })
        assert response.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        assert user.check_password("NewStrongPass456!")

    def test_change_password_wrong_old(self, authenticated_client):
        response = authenticated_client.post("/api/v1/auth/password/change/", {
            "old_password": "WrongOldPass!",
            "new_password": "NewStrongPass456!",
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_change_password_weak_new(self, authenticated_client):
        response = authenticated_client.post("/api/v1/auth/password/change/", {
            "old_password": "TestPass123!",
            "new_password": "123",
        })
        assert response.status_code == status.HTTP_400_BAD_REQUEST
