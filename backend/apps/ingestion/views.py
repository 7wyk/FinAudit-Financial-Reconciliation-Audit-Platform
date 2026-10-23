"""
Ingestion views — file upload and import management.
"""

import logging

from rest_framework import generics, parsers, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.organizations.permissions import IsMemberOfOrganization, IsOrgAdminOrManager

from .models import ImportRecord, ImportStatus
from .serializers import (
    FileUploadSerializer,
    ImportRecordSerializer,
    ImportRowErrorSerializer,
)
from .storage import generate_storage_path, get_storage_backend
from .tasks import process_import_task
from .validators import validate_upload

logger = logging.getLogger(__name__)


class FileUploadView(APIView):
    """
    Upload a CSV or XLSX file for processing.

    POST /api/v1/organizations/{org_id}/imports/upload/
    """

    permission_classes = [permissions.IsAuthenticated, IsOrgAdminOrManager]
    parser_classes = [parsers.MultiPartParser]

    def post(self, request, org_id):
        serializer = FileUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        uploaded_file = serializer.validated_data["file"]
        source = serializer.validated_data.get("source", "OTHER")

        # 1. Validate upload security
        validation = validate_upload(uploaded_file)
        if not validation["valid"]:
            return Response(
                {"error": {"code": "bad_request",
                           "message": "; ".join(validation["errors"])}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 2. Compute checksum
        checksum = ImportRecord.compute_checksum(uploaded_file)

        # 3. Check for duplicate uploads
        existing = ImportRecord.objects.filter(
            organization=request.organization,
            file_checksum=checksum,
            status__in=[
                ImportStatus.COMPLETED,
                ImportStatus.PROCESSING,
                ImportStatus.PENDING,
            ],
        ).first()
        if existing:
            return Response(
                {"error": {"code": "duplicate",
                           "message": "This file has already been uploaded.",
                           "existing_import_id": str(existing.id)}},
                status=status.HTTP_409_CONFLICT,
            )

        # 4. Upload to storage
        storage_path = generate_storage_path(str(org_id), uploaded_file.name)
        storage = get_storage_backend()

        uploaded_file.seek(0)
        file_content = uploaded_file.read()
        storage.upload(file_content, storage_path)

        # 5. Create import record
        record = ImportRecord.objects.create(
            organization=request.organization,
            uploaded_by=request.user,
            original_filename=uploaded_file.name,
            file_type=validation["file_type"],
            file_size=uploaded_file.size,
            file_checksum=checksum,
            storage_path=storage_path,
            source=source,
            status=ImportStatus.PENDING,
        )

        # 6. Queue async processing
        process_import_task.delay(str(record.id))

        return Response(
            ImportRecordSerializer(record).data,
            status=status.HTTP_201_CREATED,
        )


class ImportListView(generics.ListAPIView):
    """
    List imports for the organization.

    GET /api/v1/organizations/{org_id}/imports/
    """

    serializer_class = ImportRecordSerializer
    permission_classes = [permissions.IsAuthenticated, IsMemberOfOrganization]

    def get_queryset(self):
        return ImportRecord.objects.filter(
            organization_id=self.kwargs["org_id"],
        ).select_related("uploaded_by")


class ImportDetailView(generics.RetrieveAPIView):
    """
    Retrieve a single import record with metadata.

    GET /api/v1/organizations/{org_id}/imports/{import_id}/
    """

    serializer_class = ImportRecordSerializer
    permission_classes = [permissions.IsAuthenticated, IsMemberOfOrganization]
    lookup_url_kwarg = "import_id"

    def get_queryset(self):
        return ImportRecord.objects.filter(
            organization_id=self.kwargs["org_id"],
        ).select_related("uploaded_by")


class ImportErrorsView(generics.ListAPIView):
    """
    List row-level errors for an import.

    GET /api/v1/organizations/{org_id}/imports/{import_id}/errors/
    """

    serializer_class = ImportRowErrorSerializer
    permission_classes = [permissions.IsAuthenticated, IsMemberOfOrganization]

    def get_queryset(self):
        return (
            ImportRecord.objects.get(
                pk=self.kwargs["import_id"],
                organization_id=self.kwargs["org_id"],
            )
            .row_errors.all()
        )
