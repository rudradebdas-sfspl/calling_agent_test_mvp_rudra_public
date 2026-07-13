"""
Central configuration. ALL secrets/keys are loaded from environment (.env) here.
Nothing in this file is ever sent to the frontend — the API layer only exposes
provider/model *names*, never these values.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ----- Database -----
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/voiceagent"

    # ----- LiveKit -----
    LIVEKIT_URL: str = "ws://localhost:7880"
    LIVEKIT_PUBLIC_URL: str = ""
    LIVEKIT_API_KEY: str = ""
    LIVEKIT_API_SECRET: str = ""

    # ----- LLM: Gemini -----
    GEMINI_API_KEY: str = ""
    GEMINI_DEFAULT_MODEL: str = "gemini-3.1-flash-lite"

    # ----- Embeddings (semantic KB search) -----
    # gemini-embedding-001 -> 3072 dims by default (Matryoshka: 768/1536/3072).
    # DB column dim MUST equal EMBEDDING_DIMENSION (see migration 0006).
    EMBEDDING_MODEL: str = "models/gemini-embedding-001"
    EMBEDDING_DIMENSION: int = 3072
    EMBEDDING_BATCH_SIZE: int = 32
    # cosine similarity threshold; keep chunk only if (1 - cosine_distance) >= this
    KB_MIN_SIMILARITY_SCORE: float = 0.38
    KB_TOP_K: int = 3

    # ----- LLM: OpenAI-compatible -----
    OPENAI_COMPATIBLE_API_KEY: str = ""
    OPENAI_COMPATIBLE_BASE_URL: str = ""
    OPENAI_COMPATIBLE_DEFAULT_MODEL: str = ""

    # ----- LLM: Ollama (local) -----
    OLLAMA_BASE_URL: str = "http://host.docker.internal:11434"
    OLLAMA_DEFAULT_MODEL: str = "qwen3:8b"

    # ----- STT: Sarvam -----
    SARVAM_API_KEY: str = ""
    SARVAM_STT_DEFAULT_MODEL: str = ""
    SARVAM_STT_DEFAULT_LANGUAGE_CODE: str = "bn-IN"

    
    # Sarvam TTS (reuses SARVAM_API_KEY)
    SARVAM_TTS_DEFAULT_MODEL: str = ""
    SARVAM_TTS_DEFAULT_SPEAKER: str = ""


    # Sarvam Bulbul v3 (reuses SARVAM_API_KEY)
    SARVAM_V3_DEFAULT_SPEAKER: str = "shubh"
    SARVAM_V3_TEMPERATURE: float = 0.6
    SARVAM_V3_USE_WEBSOCKET: bool = True

    # ----- STT: Deepgram -----
    DEEPGRAM_API_KEY: str = ""
    DEEPGRAM_STT_DEFAULT_MODEL: str = "nova-3"
    DEEPGRAM_STT_DEFAULT_LANGUAGE: str = "en-IN"

    # ----- TTS: Cartesia -----
    CARTESIA_API_KEY: str = ""
    CARTESIA_MODEL: str = ""
    CARTESIA_DEFAULT_VOICE_ID: str = ""
    CARTESIA_ENGLISH_VOICE_ID: str = ""
    CARTESIA_BENGALI_VOICE_ID: str = ""
    CARTESIA_HINDI_VOICE_ID: str = ""

    # ----- TTS: shared -----
    TTS_SAMPLE_RATE: int = 8000

    # ----- Noise cancellation: Quail (ai-coustics) -----
    # License is a secret; model id is hardcoded inside the module.
    AIC_SDK_LICENSE: str = ""
    QUAIL_SDK_KEY: str = ""


    # ----- Redis / Cache -----
    CACHE_BACKEND: str = "redis"          # "redis" | "memory"
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 1                      # SIP/LiveKit DB 0 use kore — cache alada
    REDIS_PASSWORD: str = ""
    REDIS_NAMESPACE: str = "voiceagent"

    # cache TTL (seconds)
    KB_QUERY_CACHE_TTL: int = 300         # 5 min
    SESSION_TTL: int = 3600               # 1 ghonta


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()