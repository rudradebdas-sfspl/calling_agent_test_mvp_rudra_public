"""
Agent model. Holds basic details PLUS the full per-agent runtime configuration
(LLM / STT / TTS / VAD). Every runtime field has a safe default matching the spec
so existing rows and partial frontend payloads still produce a working agent.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # ---------- A. Basic details ----------
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str] = mapped_column(String(16), default="en-IN")
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_sip_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # ---------- B. Knowledgebase & Telephony ----------
    kb_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    call_transfer_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # KB documents are tracked in a separate table; this just toggles RAG.

    # ---------- C. LLM / SLM ----------
    llm_provider: Mapped[str] = mapped_column(String(64), default="gemini")
    llm_model: Mapped[str] = mapped_column(String(128), default="gemini-3.1-flash-lite")
    temperature: Mapped[float] = mapped_column(Float, default=0.4)
    max_response_tokens: Mapped[int] = mapped_column(Integer, default=512)

    # ---------- D. STT ----------
    stt_provider: Mapped[str] = mapped_column(String(64), default="sarvam")
    stt_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    stt_language_code: Mapped[str] = mapped_column(String(16), default="bn-IN")
    stt_auto_language_detection: Mapped[bool] = mapped_column(Boolean, default=False)

    # ---------- E. TTS ----------
    tts_provider: Mapped[str] = mapped_column(String(64), default="cartesia")
    cartesia_voice_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    tts_language: Mapped[str] = mapped_column(String(16), default="en")
    tts_speed: Mapped[float] = mapped_column(Float, default=1.0)
    tts_pitch: Mapped[float] = mapped_column(Float, default=0.0)
    tts_volume: Mapped[float] = mapped_column(Float, default=1.0)
    tts_emotion: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tts_tone: Mapped[str] = mapped_column(String(64), default="neutral")
    tts_style_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ---------- F. VAD / turn detection ----------
    vad_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    vad_provider: Mapped[str] = mapped_column(String(64), default="silero")
    vad_mode: Mapped[str] = mapped_column(String(32), default="normal")
    vad_threshold: Mapped[float] = mapped_column(Float, default=0.5)
    vad_min_speech_ms: Mapped[int] = mapped_column(Integer, default=250)
    vad_min_silence_ms: Mapped[int] = mapped_column(Integer, default=700)
    vad_speech_pad_ms: Mapped[int] = mapped_column(Integer, default=100)

    # ---------- G. Noise cancellation ----------
    noise_cancellation_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    noise_cancellation_provider: Mapped[str] = mapped_column(String(64), default="quail", nullable=False)

    # ---------- timestamps ----------
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
