"""
Common views — health check and other utility endpoints.
"""

from django.db import connection
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


@api_view(["GET"])
@permission_classes([AllowAny])
def health_check(request):
    """
    Basic health check endpoint.
    Returns 200 if the service and database are reachable.
    """
    health = {"status": "healthy", "database": "unknown"}

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        health["database"] = "connected"
    except Exception:
        health["database"] = "unavailable"
        return Response(health, status=status.HTTP_503_SERVICE_UNAVAILABLE)

    return Response(health, status=status.HTTP_200_OK)
