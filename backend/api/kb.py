"""KB upload & listing endpoints for a given agent."""
import os
import io
import logging
import uuid
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.agent import Agent
from backend.models.kb import KBChunk

router = APIRouter(prefix="/api/agents/{agent_id}/kb", tags=["knowledgebase"])
log = logging.getLogger("kb")

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "500"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "50"))


def _extract_text(filename: str, data: bytes) -> str:
    if filename.lower().endswith(".pdf"):
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            return "\n".join(p.extract_text() or "" for p in reader.pages)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Could not parse PDF: {exc}")
    else:
        try:
            return data.decode("utf-8", errors="replace")
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Could not decode file: {exc}")


def _chunk_text(text: str) -> list[str]:
    text = text.strip()
    chunks = []
    start = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunks.append(text[start:end].strip())
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return [c for c in chunks if c]


class KBFileInfo(BaseModel):
    filename: str
    chunk_count: int


class KBListResponse(BaseModel):
    files: List[KBFileInfo]


@router.get("", response_model=KBListResponse)
def list_kb(agent_id: uuid.UUID, db: Session = Depends(get_db)):
    _get_agent_or_404(agent_id, db)
    rows = (
        db.query(KBChunk.filename, KBChunk.chunk_index)
        .filter(KBChunk.agent_id == agent_id)
        .all()
    )
    file_counts: dict[str, int] = {}
    for filename, _ in rows:
        file_counts[filename] = file_counts.get(filename, 0) + 1
    return KBListResponse(
        files=[KBFileInfo(filename=k, chunk_count=v) for k, v in file_counts.items()]
    )


@router.post("", status_code=201)
async def upload_kb(
    agent_id: uuid.UUID,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    _get_agent_or_404(agent_id, db)

    inserted = 0
    for upload in files:
        data = await upload.read()
        text = _extract_text(upload.filename or "file.txt", data)
        chunks = _chunk_text(text)

        # Remove old chunks for this file (re-upload replaces them)
        db.query(KBChunk).filter(
            KBChunk.agent_id == agent_id,
            KBChunk.filename == upload.filename,
        ).delete()

        # Embed all chunks of this file (best-effort). If embedding fails, chunks
        # are still stored without vectors — run backfill_embeddings.py later.
        embeddings = None
        if hasattr(KBChunk, "embedding") and chunks:
            try:
                from backend.services.embeddings import embed_texts
                embeddings = await embed_texts(chunks, task_type="RETRIEVAL_DOCUMENT")
            except Exception:
                log.exception("embedding generation failed for %s — storing without vectors", upload.filename)
                embeddings = None

        for i, chunk in enumerate(chunks):
            row_kwargs = dict(
                agent_id=agent_id,
                filename=upload.filename or "file.txt",
                chunk_index=i,
                content=chunk,
                created_at=datetime.utcnow(),
            )
            if embeddings is not None and i < len(embeddings):
                row_kwargs["embedding"] = embeddings[i]
            db.add(KBChunk(**row_kwargs))
        inserted += len(chunks)

    db.commit()
    return {"inserted_chunks": inserted}


@router.delete("/{filename}", status_code=204)
def delete_kb_file(agent_id: uuid.UUID, filename: str, db: Session = Depends(get_db)):
    _get_agent_or_404(agent_id, db)
    db.query(KBChunk).filter(
        KBChunk.agent_id == agent_id,
        KBChunk.filename == filename,
    ).delete()
    db.commit()


def _get_agent_or_404(agent_id: uuid.UUID, db: Session) -> Agent:
    agent = db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent
