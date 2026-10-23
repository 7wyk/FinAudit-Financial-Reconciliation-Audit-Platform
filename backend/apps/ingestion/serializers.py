"""
Ingestion serializers — import records and upload handling.
"""

from rest_framework import serializers

from .models import ImportRecord, ImportRowError, ImportSource


class ImportRecordSerializer(serializers.ModelSerializer):
    uploaded_by_email = serializers.EmailField(
        source="uploaded_by.email", read_only=True
    )
    error_count = serializers.SerializerMethodField()

    class Meta:
        model = ImportRecord
        fields = (
            "id", "organization", "uploaded_by", "uploaded_by_email",
            "original_filename", "file_type", "file_size", "file_checksum",
            "source", "status",
            "total_rows", "valid_rows", "rejected_rows",
            "processing_started_at", "processing_completed_at",
            "error_message", "error_count",
            "created_at", "updated_at",
        )
        read_only_fields = fields

    def get_error_count(self, obj):
        return obj.row_errors.count()


class ImportRowErrorSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImportRowError
        fields = (
            "id", "row_number", "field_name", "error_type",
            "error_message", "raw_value",
        )
        read_only_fields = fields


class FileUploadSerializer(serializers.Serializer):
    """Handles multipart file upload validation."""

    file = serializers.FileField()
    source = serializers.ChoiceField(
        choices=ImportSource.choices,
        default=ImportSource.OTHER,
    )
