"""Safe handling of uploaded documents.

* The file type is decided by looking at the bytes, never by the client-supplied
  extension or Content-Type.
* Files are stored under server-generated names inside `upload_dir/<user_id>/`,
  so a hostile filename can never influence a path.
"""
import os
import re
import uuid
from pathlib import Path

from ..config import get_settings
from ..constants import ALLOWED_UPLOAD_KINDS


def detect_kind(data: bytes) -> str | None:
    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if b"\x00" not in data:
        try:
            data.decode("utf-8")
            return "text"
        except UnicodeDecodeError:
            return None
    return None


def clean_filename(name: str | None) -> str:
    """Display-only name: strip any directory part and control characters."""
    base = os.path.basename((name or "").replace("\\", "/"))
    base = re.sub(r"[\x00-\x1f\x7f]", "", base).strip()
    return base[:255] or "document"


def _root() -> Path:
    root = get_settings().upload_dir
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def store_file(user_id: str, data: bytes, kind: str) -> tuple[str, str]:
    """Write bytes to disk. Returns (path relative to upload_dir, content_type)."""
    ext, content_type = ALLOWED_UPLOAD_KINDS[kind]
    rel = f"{user_id}/{uuid.uuid4().hex}{ext}"
    target = _root() / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return rel, content_type


def resolve_file(rel: str) -> Path | None:
    """Absolute path for a stored file, or None if it escapes the upload dir / is missing."""
    root = _root()
    path = (root / rel).resolve()
    if root not in path.parents or not path.is_file():
        return None
    return path


def delete_file(rel: str) -> None:
    path = resolve_file(rel)
    if path is not None:
        path.unlink(missing_ok=True)
