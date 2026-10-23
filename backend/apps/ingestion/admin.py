from django.contrib import admin

from .models import ImportRecord, ImportRowError


@admin.register(ImportRecord)
class ImportRecordAdmin(admin.ModelAdmin):
    list_display = (
        "original_filename", "organization", "status",
        "total_rows", "valid_rows", "rejected_rows", "created_at",
    )
    list_filter = ("status", "source", "file_type")
    search_fields = ("original_filename", "file_checksum")
    readonly_fields = ("file_checksum", "storage_path")


@admin.register(ImportRowError)
class ImportRowErrorAdmin(admin.ModelAdmin):
    list_display = ("import_record", "row_number", "field_name", "error_type")
    list_filter = ("error_type",)
