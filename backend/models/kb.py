"""KBChunk — stores extracted text chunks for per-agent knowledgebases."""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.config import settings
from backend.database import Base

# pgvector's SQLAlchemy type. Import is guarded so the app can still import this
# module in environments where pgvector isn't installed yet (e.g. before setup).
try:
    from pgvector.sqlalchemy import HALFVEC

    _EMBEDDING_TYPE = HALFVEC(settings.EMBEDDING_DIMENSION)
except Exception:  # pragma: no cover
    _EMBEDDING_TYPE = None


class KBChunk(Base):
    __tablename__ = "kb_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Semantic search vector (halfvec(EMBEDDING_DIMENSION)). Nullable so old rows
    # without embeddings still load; run backfill_embeddings.py to populate them.
    if _EMBEDDING_TYPE is not None:
        embedding: Mapped[list[float] | None] = mapped_column(
            _EMBEDDING_TYPE, nullable=True
        )