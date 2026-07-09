"""add agent runtime configuration (llm/stt/tts/vad)

Revision ID: 0001_add_agent_runtime_config
Revises:
Create Date: 2026-06-22

This migration creates the `agents` table with the full runtime configuration.

If you ALREADY have an `agents` (or `agent_settings`) table, do NOT recreate it —
instead replace the create_table below with the op.add_column() block at the
bottom of this file (kept commented for that case). The column set, types, and
safe defaults are identical either way.
"""
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0001_add_agent_runtime_config"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        # A. basic
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("language", sa.String(16), server_default="en-IN", nullable=False),
        sa.Column("system_prompt", sa.Text(), server_default="", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        # B. knowledgebase
        sa.Column("kb_enabled", sa.Boolean(), server_default=sa.false(), nullable=False),
        # C. LLM
        sa.Column("llm_provider", sa.String(64), server_default="gemini", nullable=False),
        sa.Column("llm_model", sa.String(128), server_default="gemini-3.1-flash-lite", nullable=False),
        sa.Column("temperature", sa.Float(), server_default="0.4", nullable=False),
        sa.Column("max_response_tokens", sa.Integer(), server_default="512", nullable=False),
        # D. STT
        sa.Column("stt_provider", sa.String(64), server_default="sarvam", nullable=False),
        sa.Column("stt_model", sa.String(128), nullable=True),
        sa.Column("stt_language_code", sa.String(16), server_default="bn-IN", nullable=False),
        sa.Column("stt_auto_language_detection", sa.Boolean(), server_default=sa.false(), nullable=False),
        # E. TTS
        sa.Column("tts_provider", sa.String(64), server_default="cartesia", nullable=False),
        sa.Column("cartesia_voice_id", sa.String(128), nullable=True),
        sa.Column("tts_language", sa.String(16), server_default="en", nullable=False),
        sa.Column("tts_speed", sa.Float(), server_default="1.0", nullable=False),
        sa.Column("tts_pitch", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("tts_volume", sa.Float(), server_default="1.0", nullable=False),
        sa.Column("tts_emotion", sa.String(64), nullable=True),
        sa.Column("tts_tone", sa.String(64), server_default="neutral", nullable=False),
        sa.Column("tts_style_prompt", sa.Text(), nullable=True),
        # F. VAD
        sa.Column("vad_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("vad_provider", sa.String(64), server_default="silero", nullable=False),
        sa.Column("vad_mode", sa.String(32), server_default="normal", nullable=False),
        sa.Column("vad_threshold", sa.Float(), server_default="0.5", nullable=False),
        sa.Column("vad_min_speech_ms", sa.Integer(), server_default="250", nullable=False),
        sa.Column("vad_min_silence_ms", sa.Integer(), server_default="700", nullable=False),
        sa.Column("vad_speech_pad_ms", sa.Integer(), server_default="100", nullable=False),
        # timestamps
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("agents")


# ---------------------------------------------------------------------------
# IF YOU ALREADY HAVE AN agents TABLE, use this instead of create_table above:
#
# def upgrade() -> None:
#     op.add_column("agents", sa.Column("llm_provider", sa.String(64), server_default="gemini", nullable=False))
#     op.add_column("agents", sa.Column("llm_model", sa.String(128), server_default="gemini-3.1-flash-lite", nullable=False))
#     op.add_column("agents", sa.Column("temperature", sa.Float(), server_default="0.4", nullable=False))
#     op.add_column("agents", sa.Column("max_response_tokens", sa.Integer(), server_default="512", nullable=False))
#     op.add_column("agents", sa.Column("stt_provider", sa.String(64), server_default="sarvam", nullable=False))
#     op.add_column("agents", sa.Column("stt_model", sa.String(128), nullable=True))
#     op.add_column("agents", sa.Column("stt_language_code", sa.String(16), server_default="bn-IN", nullable=False))
#     op.add_column("agents", sa.Column("stt_auto_language_detection", sa.Boolean(), server_default=sa.false(), nullable=False))
#     op.add_column("agents", sa.Column("tts_provider", sa.String(64), server_default="cartesia", nullable=False))
#     op.add_column("agents", sa.Column("cartesia_voice_id", sa.String(128), nullable=True))
#     op.add_column("agents", sa.Column("tts_language", sa.String(16), server_default="en", nullable=False))
#     op.add_column("agents", sa.Column("tts_speed", sa.Float(), server_default="1.0", nullable=False))
#     op.add_column("agents", sa.Column("tts_pitch", sa.Float(), server_default="0.0", nullable=False))
#     op.add_column("agents", sa.Column("tts_volume", sa.Float(), server_default="1.0", nullable=False))
#     op.add_column("agents", sa.Column("tts_emotion", sa.String(64), nullable=True))
#     op.add_column("agents", sa.Column("tts_tone", sa.String(64), server_default="neutral", nullable=False))
#     op.add_column("agents", sa.Column("tts_style_prompt", sa.Text(), nullable=True))
#     op.add_column("agents", sa.Column("vad_mode", sa.String(32), server_default="normal", nullable=False))
#     op.add_column("agents", sa.Column("vad_threshold", sa.Float(), server_default="0.5", nullable=False))
#     op.add_column("agents", sa.Column("vad_min_speech_ms", sa.Integer(), server_default="250", nullable=False))
#     op.add_column("agents", sa.Column("vad_min_silence_ms", sa.Integer(), server_default="700", nullable=False))
#     op.add_column("agents", sa.Column("vad_speech_pad_ms", sa.Integer(), server_default="100", nullable=False))
# ---------------------------------------------------------------------------
