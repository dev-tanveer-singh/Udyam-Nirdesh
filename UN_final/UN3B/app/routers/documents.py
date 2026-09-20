from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select

from ..config import get_settings
from ..constants import DOCUMENT_TYPES
from ..deps import DB, EntrepreneurUser
from ..models import Document
from ..schemas import DocumentListOut, DocumentStatusOut
from ..services import documents as store

router = APIRouter(prefix="/documents", tags=["documents"])


def _status_row(slug: str, doc: Document | None) -> DocumentStatusOut:
    if doc is None:
        return DocumentStatusOut(type=slug, label=DOCUMENT_TYPES[slug], status="missing")
    return DocumentStatusOut(
        type=slug, label=DOCUMENT_TYPES[slug], status="uploaded", document_id=doc.id,
        filename=doc.original_filename, size_bytes=doc.size_bytes, uploaded_at=doc.uploaded_at,
    )


def _own_document(db, user_id: str, document_id: str) -> Document:
    doc = db.scalar(select(Document).where(Document.id == document_id, Document.user_id == user_id))
    if doc is None:  # same answer for "not yours" and "does not exist"
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found")
    return doc


@router.get("", response_model=DocumentListOut)
def list_documents(user: EntrepreneurUser, db: DB):
    """The full checklist: every document type, marked uploaded or missing."""
    by_type = {d.document_type: d for d in db.scalars(select(Document).where(Document.user_id == user.id))}
    rows = [_status_row(slug, by_type.get(slug)) for slug in DOCUMENT_TYPES]
    uploaded = sum(r.status == "uploaded" for r in rows)
    return DocumentListOut(documents=rows, completion_pct=round(uploaded / len(rows) * 100))


@router.post("/upload", response_model=DocumentStatusOut, status_code=status.HTTP_201_CREATED)
def upload_document(
    user: EntrepreneurUser,
    db: DB,
    document_type: Annotated[str, Form()],
    file: Annotated[UploadFile, File()],
):
    """multipart/form-data: `document_type` (slug) + `file`. Re-uploading a type replaces the old file."""
    if document_type not in DOCUMENT_TYPES:
        raise HTTPException(422, f"Unknown document_type. Use one of: {', '.join(DOCUMENT_TYPES)}")

    limit = get_settings().max_upload_bytes
    data = file.file.read(limit + 1)      # never read more than limit+1 bytes into memory
    if not data:
        raise HTTPException(422, "The uploaded file is empty.")
    if len(data) > limit:
        raise HTTPException(413, f"File is too large (max {limit // (1024 * 1024)} MB).")
    kind = store.detect_kind(data)
    if kind is None:
        raise HTTPException(415, "Unsupported file. Upload a PDF, PNG, JPG or plain-text file.")

    rel_path, content_type = store.store_file(user.id, data, kind)
    existing = db.scalar(select(Document).where(Document.user_id == user.id, Document.document_type == document_type))
    old_path = existing.stored_path if existing else None
    try:
        doc = existing or Document(user_id=user.id, document_type=document_type)
        doc.original_filename = store.clean_filename(file.filename)
        doc.stored_path = rel_path
        doc.content_type = content_type
        doc.size_bytes = len(data)
        db.add(doc)
        db.commit()
    except Exception:
        db.rollback()
        store.delete_file(rel_path)
        raise
    if old_path:
        store.delete_file(old_path)
    db.refresh(doc)
    return _status_row(document_type, doc)


@router.get("/{document_id}/file")
def download_document(document_id: str, user: EntrepreneurUser, db: DB):
    doc = _own_document(db, user.id, document_id)
    path = store.resolve_file(doc.stored_path)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The stored file is missing. Please upload it again.")
    return FileResponse(
        path,
        media_type=doc.content_type,
        filename=doc.original_filename,
        content_disposition_type="inline",
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"},
    )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: str, user: EntrepreneurUser, db: DB):
    doc = _own_document(db, user.id, document_id)
    rel = doc.stored_path
    db.delete(doc)
    db.commit()
    store.delete_file(rel)
