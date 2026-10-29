"""Upload validators: extension, content type, 10 MB limit."""
import os

from django.conf import settings
from django.core.exceptions import ValidationError
from django.template.defaultfilters import filesizeformat

# extension -> (accepted browser content types, magic-byte signature, canonical MIME)
FILE_SIGNATURES = {
    ".pdf": ({"application/pdf", "application/x-pdf"}, (b"%PDF",), "application/pdf"),
    ".png": ({"image/png"}, (b"\x89PNG\r\n\x1a\n",), "image/png"),
    ".jpg": ({"image/jpeg", "image/pjpeg"}, (b"\xff\xd8\xff",), "image/jpeg"),
    ".jpeg": ({"image/jpeg", "image/pjpeg"}, (b"\xff\xd8\xff",), "image/jpeg"),
}


def validate_upload(uploaded_file):
    """Validate size, extension, declared content type, and actual file signature.

    Returns the canonical MIME type of the file.
    """
    max_size = settings.MAX_UPLOAD_SIZE
    if uploaded_file.size > max_size:
        raise ValidationError(
            f"File is too large ({filesizeformat(uploaded_file.size)}). Maximum is {filesizeformat(max_size)}."
        )
    if uploaded_file.size == 0:
        raise ValidationError("The uploaded file is empty.")

    ext = os.path.splitext(uploaded_file.name)[1].lower()
    allowed = [e.lower() for e in settings.ALLOWED_UPLOAD_EXTENSIONS]
    if ext not in allowed or ext not in FILE_SIGNATURES:
        raise ValidationError("Only PDF, JPG, and PNG files are allowed.")

    content_types, signatures, canonical = FILE_SIGNATURES[ext]
    declared = (getattr(uploaded_file, "content_type", "") or "").lower()
    if declared and declared not in content_types:
        raise ValidationError(f"File content type '{declared}' does not match the {ext} extension.")

    uploaded_file.seek(0)
    head = uploaded_file.read(16)
    uploaded_file.seek(0)
    if not any(head.startswith(sig) for sig in signatures):
        raise ValidationError("The file content does not match its extension (file may be corrupted or renamed).")
    return canonical
