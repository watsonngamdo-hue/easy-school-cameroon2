"""Validation des fichiers envoyés par les utilisateurs."""
import os

from django.core.exceptions import ValidationError

SIGNATURES = {
    ".pdf": (b"%PDF",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".webp": (b"RIFF",),
    ".docx": (b"PK\x03\x04",),
    ".xlsx": (b"PK\x03\x04",),
    ".zip": (b"PK\x03\x04",),
    ".rar": (b"Rar!\x1a\x07",),
}


def validate_upload(f, allowed_extensions, max_mb=10):
    """Vérifie l'extension, la taille et la signature binaire (« magic bytes »)
    du fichier, pour empêcher par exemple un .html déguisé en .pdf."""
    if not f:
        return f
    ext = os.path.splitext(f.name or "")[1].lower()
    if ext not in allowed_extensions:
        raise ValidationError(f"Extension « {ext or '?'} » non autorisée.")
    if f.size > max_mb * 1024 * 1024:
        raise ValidationError(f"Fichier trop volumineux ({max_mb} Mo maximum).")
    signatures = SIGNATURES.get(ext)
    if signatures:
        head = f.read(16)
        f.seek(0)
        if not any(head.startswith(sig) for sig in signatures):
            raise ValidationError("Le contenu du fichier ne correspond pas à son extension.")
    elif ext == ".txt":
        head = f.read(2048)
        f.seek(0)
        if b"<script" in head.lower() or b"<html" in head.lower():
            raise ValidationError("Contenu texte non autorisé.")
    return f
