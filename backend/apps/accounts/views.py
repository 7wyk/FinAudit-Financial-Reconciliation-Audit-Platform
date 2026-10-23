"""
Account views — registration, profile, password change.
"""

from django.contrib.auth import get_user_model
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import UserRegistrationSerializer, UserSerializer

User = get_user_model()


class RegisterView(generics.CreateAPIView):
    """Register a new user account."""

    serializer_class = UserRegistrationSerializer
    permission_classes = (permissions.AllowAny,)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(
            UserSerializer(user).data,
            status=status.HTTP_201_CREATED,
        )


class ProfileView(generics.RetrieveAPIView):
    """Retrieve the authenticated user's profile."""

    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


class PasswordChangeView(APIView):
    """Change password for the authenticated user."""

    def post(self, request):
        user = request.user
        old_password = request.data.get("old_password")
        new_password = request.data.get("new_password")

        if not old_password or not new_password:
            return Response(
                {"error": {"code": "bad_request",
                           "message": "old_password and new_password required."}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not user.check_password(old_password):
            return Response(
                {"error": {"code": "bad_request",
                           "message": "Current password is incorrect."}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError

        try:
            validate_password(new_password, user)
        except ValidationError as e:
            return Response(
                {"error": {"code": "bad_request",
                           "message": "; ".join(e.messages)}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.set_password(new_password)
        user.save()
        return Response({"message": "Password updated successfully."})
