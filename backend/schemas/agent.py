"""
Request/response schemas for the Agent Builder.

Validation rules enforced here (per spec):
  - llm_provider / stt_provider / tts_provider must be from the supported sets.
  - vad_mode must be a known mode; when a preset is chosen, the threshold/timing
    columns are normalised to the preset so the DB stays self-consistent.
  - No API keys appear anywhere in these schemas — only provider/model names.
"""
import uuid
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.services.vad.presets import PRESETS, VAD_MODES

SUPPORTED_LLM_PROVIDERS = {"gemini", "openai-compatible", "local-ollama", "sarvam-slm"}
SUPPORTED_STT_PROVIDERS = {"sarvam", "deepgram"}
SUPPORTED_TTS_PROVIDERS = {"cartesia", "sarvam", "sarvam-v3"}
SUPPORTED_NC_PROVIDERS = {"quail"}
SUPPORTED_TONES = {
    "neutral", "professional", "friendly", "calm", "energetic",
    "empathetic", "serious", "support-agent", "sales-agent", "custom",
}


class AgentBase(BaseModel):
    # A. basic
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    language: str = "en-IN"
    system_prompt: str = ""
    is_active: bool = True
    is_sip_default: bool = False

    # B. knowledgebase & telephony
    kb_enabled: bool = False
    call_transfer_number: Optional[str] = None

    # C. LLM
    llm_provider: str = "gemini"
    llm_model: str = "gemini-3.1-flash-lite"
    temperature: float = Field(default=0.4, ge=0.0, le=2.0)
    max_response_tokens: int = Field(default=512, ge=16, le=8192)

    # D. STT
    stt_provider: str = "sarvam"
    stt_model: Optional[str] = None
    stt_language_code: str = "bn-IN"
    stt_auto_language_detection: bool = False

    # E. TTS
    tts_provider: str = "cartesia"
    cartesia_voice_id: Optional[str] = None
    tts_language: str = "en"
    tts_speed: float = Field(default=1.0, ge=0.25, le=3.0)
    tts_pitch: float = Field(default=0.0, ge=-12.0, le=12.0)
    tts_volume: float = Field(default=1.0, ge=0.0, le=2.0)
    tts_emotion: Optional[str] = None
    tts_tone: str = "neutral"
    tts_style_prompt: Optional[str] = None

    # F. VAD
    vad_enabled: bool = True
    vad_provider: str = "silero"
    vad_mode: str = "normal"
    vad_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    vad_min_speech_ms: int = Field(default=250, ge=0, le=5000)
    vad_min_silence_ms: int = Field(default=700, ge=0, le=5000)
    vad_speech_pad_ms: int = Field(default=100, ge=0, le=2000)

    # G. Noise cancellation
    noise_cancellation_enabled: bool = False
    noise_cancellation_provider: str = "quail"

    @field_validator("llm_provider")
    @classmethod
    def _v_llm(cls, v):
        if v not in SUPPORTED_LLM_PROVIDERS:
            raise ValueError(f"Unsupported llm_provider '{v}'. Allowed: {sorted(SUPPORTED_LLM_PROVIDERS)}")
        return v

    @field_validator("noise_cancellation_provider")
    @classmethod
    def _validate_nc_provider(cls, v):
        if v not in SUPPORTED_NC_PROVIDERS:
            raise ValueError(f"Unsupported noise_cancellation_provider '{v}'. Allowed: {sorted(SUPPORTED_NC_PROVIDERS)}")
        return v

    @field_validator("stt_provider")
    @classmethod
    def _v_stt(cls, v):
        if v not in SUPPORTED_STT_PROVIDERS:
            raise ValueError(f"Unsupported stt_provider '{v}'. Allowed: {sorted(SUPPORTED_STT_PROVIDERS)}")
        return v

    @field_validator("tts_provider")
    @classmethod
    def _v_tts(cls, v):
        if v not in SUPPORTED_TTS_PROVIDERS:
            raise ValueError(f"Unsupported tts_provider '{v}'. Allowed: {sorted(SUPPORTED_TTS_PROVIDERS)}")
        return v

    @field_validator("tts_tone")
    @classmethod
    def _v_tone(cls, v):
        if v not in SUPPORTED_TONES:
            raise ValueError(f"Unsupported tts_tone '{v}'. Allowed: {sorted(SUPPORTED_TONES)}")
        return v

    @field_validator("vad_mode")
    @classmethod
    def _v_vad_mode(cls, v):
        if v not in VAD_MODES:
            raise ValueError(f"Unsupported vad_mode '{v}'. Allowed: {VAD_MODES}")
        return v

    @model_validator(mode="after")
    def _normalise_vad(self):
        """When a preset is chosen, snap the stored numeric fields to the preset."""
        if self.vad_mode in PRESETS:
            p = PRESETS[self.vad_mode]
            self.vad_threshold = p.threshold
            self.vad_min_speech_ms = p.min_speech_ms
            self.vad_min_silence_ms = p.min_silence_ms
            self.vad_speech_pad_ms = p.speech_pad_ms
        return self


class AgentCreate(AgentBase):
    pass


class AgentUpdate(AgentBase):
    pass


class AgentRead(AgentBase):
    id: uuid.UUID

    model_config = {"from_attributes": True}
