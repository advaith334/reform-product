"""HTTP endpoints."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from . import repository, storage
from .schemas import DocumentDetail, DocumentSummary, UploadAccepted
from .service import process_upload

router = APIRouter()


def _pool(request: Request):
    return request.app.state.pool


@router.get("/health")
def health(request: Request) -> dict[str, str]:
    with _pool(request).connection() as conn, conn.cursor() as cur:
        cur.execute("select 1 as ok")
        cur.fetchone()
    return {"status": "ok"}


@router.post("/documents", response_model=UploadAccepted, status_code=202)
async def upload_document(
    request: Request,
    background: BackgroundTasks,
    file: UploadFile = File(...),
) -> UploadAccepted:
    """Accept a document and start extracting it.

    Returns as soon as the bytes are on disk. OCR plus extraction takes tens of
    seconds, far too long to hold a request open, so the client polls
    ``GET /documents/{id}`` until ``status`` leaves 'pending'/'processing'.
    """
    data = await file.read()
    try:
        suffix = storage.validate(file.filename or "", file.content_type, len(data))
    except storage.UploadRejected as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    stored_name, path = storage.save(data, suffix)

    with _pool(request).connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            insert into documents (
                source_file, original_filename, stored_path, content_type, status
            )
            values (%s, %s, %s, %s, 'pending')
            returning id
            """,
            (
                stored_name,
                file.filename or stored_name,
                f"uploads/{stored_name}",
                file.content_type,
            ),
        )
        document_id = str(cur.fetchone()["id"])

    background.add_task(process_upload, _pool(request), document_id, path)

    return UploadAccepted(
        id=document_id,
        status="pending",
        original_filename=file.filename or stored_name,
    )


@router.get("/documents", response_model=list[DocumentSummary])
def list_documents(request: Request) -> list[DocumentSummary]:
    with _pool(request).connection() as conn:
        return repository.list_documents(conn)


@router.get("/documents/{document_id}", response_model=DocumentDetail)
def get_document(request: Request, document_id: str) -> DocumentDetail:
    with _pool(request).connection() as conn:
        document = repository.get_document(conn, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@router.get("/documents/{document_id}/file")
def get_document_file(request: Request, document_id: str) -> FileResponse:
    """Serve the original document so the UI can show it beside the extracted fields."""
    with _pool(request).connection() as conn:
        row: dict[str, Any] | None = repository.get_file_location(conn, document_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Document not found")

    path: Path | None = storage.resolve(row["stored_path"], row["source_file"])
    if path is None:
        raise HTTPException(status_code=404, detail="The original file is no longer on disk")

    return FileResponse(
        path,
        media_type=row["content_type"] or "application/pdf",
        # inline, so an <iframe> renders it rather than the browser downloading it.
        headers={
            "Content-Disposition": (
                f'inline; filename="{row["original_filename"] or row["source_file"]}"'
            )
        },
    )


@router.delete("/documents/{document_id}", status_code=204)
def delete_document(request: Request, document_id: str) -> None:
    with _pool(request).connection() as conn, conn.cursor() as cur:
        # Line items and confidence rows go with it via on delete cascade.
        cur.execute(
            "delete from documents where id = %s returning stored_path",
            (document_id,),
        )
        row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Document not found")
    storage.delete(row["stored_path"])
