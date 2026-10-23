"""
Organization serializers — org CRUD and membership management.
"""

from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Membership, MembershipRole, Organization

User = get_user_model()


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ("id", "name", "slug", "is_active", "created_at", "updated_at")
        read_only_fields = ("id", "created_at", "updated_at")


class OrganizationCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ("id", "name", "slug")
        read_only_fields = ("id",)

    def create(self, validated_data):
        user = self.context["request"].user
        org = Organization.objects.create(**validated_data)
        # Creator becomes ADMIN
        Membership.objects.create(
            user=user,
            organization=org,
            role=MembershipRole.ADMIN,
        )
        return org


class MembershipSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source="user.email", read_only=True)
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = Membership
        fields = ("id", "user", "user_email", "user_name", "organization",
                  "role", "is_active", "created_at")
        read_only_fields = ("id", "created_at")

    def get_user_name(self, obj):
        return f"{obj.user.first_name} {obj.user.last_name}".strip() or obj.user.username


class MembershipCreateSerializer(serializers.Serializer):
    """Add a user to an organization by email."""

    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=MembershipRole.choices)

    def validate_email(self, value):
        try:
            self.user_obj = User.objects.get(email=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("User with this email does not exist.")
        return value

    def create(self, validated_data):
        org = self.context["organization"]
        membership, created = Membership.objects.get_or_create(
            user=self.user_obj,
            organization=org,
            defaults={"role": validated_data["role"]},
        )
        if not created:
            raise serializers.ValidationError(
                {"email": "User is already a member of this organization."}
            )
        return membership
