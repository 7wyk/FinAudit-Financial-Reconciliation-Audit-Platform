"""
File upload validation — security checks before processing.

Validates files safely. Does not trust filenames, MIME types, extensions,
uploaded content, or client-supplied metadata.
"""

import logging
import os

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {"csv", "xlsx"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

# Magic bytes for file type detection
MAGIC_BYTES = {
    "xlsx": [b"PK\x03\x04"],  # ZIP-based format
    "csv": [],  # CSV has no magic bytes; validated by parsing
}


def validate_upload(uploaded_file) -> dict:
    """
    Validate an uploaded file for security and format compliance.

    Returns: {"valid": bool, "file_type": str, "errors": list[str]}
    """
    errors = []
    filename = uploaded_file.name or ""
    file_size = uploaded_file.size

    # 1. Filename safety — strip path components, check extension
    safe_name = os.path.basename(filename)
    ext = os.path.splitext(safe_name)[1].lower().lstrip(".")

    if not ext:
        errors.append("File has no extension.")
    elif ext not in ALLOWED_EXTENSIONS:
        errors.append(
            f"File type '.{ext}' is not supported. "
            f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    # 2. File size check
    if file_size <= 0:
        errors.append("File is empty.")
    elif file_size > MAX_FILE_SIZE:
        errors.append(
            f"File size ({file_size / 1024 / 1024:.1f} MB) "
            f"exceeds maximum ({MAX_FILE_SIZE / 1024 / 1024:.0f} MB)."
        )

    # 3. Magic bytes check for XLSX
    if ext == "xlsx" and not errors:
        uploaded_file.seek(0)
        header = uploaded_file.read(4)
        uploaded_file.seek(0)
        if header != b"PK\x03\x04":
            errors.append(
                "File content does not match XLSX format. "
                "The file may be corrupt or misnamed."
            )

    # 4. Null bytes check — prevents path traversal in filenames
    if "\x00" in filename:
        errors.append("Filename contains null bytes.")

    file_type = ext if ext in ALLOWED_EXTENSIONS else ""

    return {
        "valid": len(errors) == 0,
        "file_type": file_type,
        "errors": errors,
    }
