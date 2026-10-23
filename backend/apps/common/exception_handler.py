"""
Custom DRF exception handler for consistent API error responses.
"""

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    """
    Wrap DRF exceptions in a consistent envelope:
    {
        "error": {
            "code": "...",
            "message": "...",
            "details": { ... }  // optional
        }
    }
    """
    response = exception_handler(exc, context)

    if response is None:
        return Response(
            {
                "error": {
                    "code": "internal_error",
                    "message": "An unexpected error occurred.",
                }
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    error_body = {
        "error": {
            "code": _status_to_code(response.status_code),
            "message": _extract_message(response.data),
        }
    }

    # Preserve field-level validation details
    if isinstance(response.data, dict) and any(
        isinstance(v, list) for v in response.data.values()
    ):
        error_body["error"]["details"] = response.data

    response.data = error_body
    return response


def _status_to_code(status_code: int) -> str:
    mapping = {
        400: "bad_request",
        401: "unauthorized",
        403: "forbidden",
        404: "not_found",
        405: "method_not_allowed",
        429: "throttled",
    }
    return mapping.get(status_code, f"error_{status_code}")


def _extract_message(data) -> str:
    if isinstance(data, dict):
        detail = data.get("detail")
        if detail:
            return str(detail)
        # Concatenate field errors
        messages = []
        for field, errors in data.items():
            if isinstance(errors, list):
                messages.append(f"{field}: {'; '.join(str(e) for e in errors)}")
            else:
                messages.append(f"{field}: {errors}")
        return "; ".join(messages) if messages else "Validation error."
    if isinstance(data, list):
        return "; ".join(str(e) for e in data)
    return str(data)
