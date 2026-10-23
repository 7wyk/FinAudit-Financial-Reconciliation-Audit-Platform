"""
Account serializers — registration, user profile, JWT token customization.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

User = get_user_model()


class UserRegistrationSerializer(serializers.ModelSerializer):
    """Handles user registration with password validation."""

    password = serializers.CharField(
        write_only=True, min_length=8, validators=[validate_password]
    )
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ("id", "email", "username", "first_name", "last_name",
                  "password", "password_confirm")
        read_only_fields = ("id",)

    def validate(self, attrs):
        if attrs["password"] != attrs.pop("password_confirm"):
            raise serializers.ValidationError(
                {"password_confirm": "Passwords do not match."}
            )
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class UserSerializer(serializers.ModelSerializer):
    """Read-only user representation."""

    class Meta:
        model = User
        fields = ("id", "email", "username", "first_name", "last_name",
                  "is_active", "date_joined")
        read_only_fields = fields
