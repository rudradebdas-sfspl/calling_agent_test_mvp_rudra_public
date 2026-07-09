// Option lists shown in the Agent Builder. These mirror the backend's supported
// sets and act as a FALLBACK when GET /api/providers is unavailable. When that
// endpoint responds, the provider dropdowns use its (capability-aware) list.
// No API keys here — only provider/model/tone names.

export const LLM_PROVIDERS = [
  { value: "gemini", label: "Gemini" },
  { value: "openai-compatible", label: "OpenAI-compatible" },
  { value: "local-ollama", label: "Local (Ollama)" },
  { value: "sarvam-slm", label: "Sarvam SLM (if available)" },
];

// Suggested models per provider (free-text also allowed).
export const LLM_MODEL_SUGGESTIONS = {
  gemini: ["gemini-3.1-flash-lite"],
  "openai-compatible": [],
  "local-ollama": ["qwen3:8b"],
  "sarvam-slm": [],
};

export const STT_PROVIDERS = [
  { value: "sarvam", label: "Sarvam" },
  { value: "deepgram", label: "Deepgram" },
];

export const STT_MODEL_SUGGESTIONS = {
  sarvam: [],
  deepgram: ["nova-3"],
};

export const TTS_PROVIDERS = [
  { value: "cartesia", label: "Cartesia" },
  { value: "sarvam", label: "Sarvam (v2)" },
  { value: "sarvam-v3", label: "Sarvam Bulbul v3" },
];

export const TTS_TONES = [
  "neutral",
  "professional",
  "friendly",
  "calm",
  "energetic",
  "empathetic",
  "serious",
  "support-agent",
  "sales-agent",
  "custom",
];

export const VAD_MODES = [
  { value: "low_sensitivity", label: "Low sensitivity (noisy rooms)" },
  { value: "normal", label: "Normal (default — office/browser mic)" },
  { value: "aggressive", label: "Aggressive (faster)" },
  { value: "very_aggressive", label: "Very aggressive (low-latency demos)" },
  { value: "custom", label: "Custom" },
];

// Default new-agent payload (matches backend safe defaults).
export const DEFAULT_AGENT = {
  name: "",
  description: "",
  language: "en-IN",
  system_prompt: "",
  is_active: true,

  kb_enabled: false,

  llm_provider: "gemini",
  llm_model: "gemini-3.1-flash-lite",
  temperature: 0.4,
  max_response_tokens: 512,

  stt_provider: "sarvam",
  stt_model: "",
  stt_language_code: "bn-IN",
  stt_auto_language_detection: false,

  tts_provider: "cartesia",
  cartesia_voice_id: "",
  tts_language: "en",
  tts_speed: 1.0,
  tts_pitch: 0.0,
  tts_volume: 1.0,
  tts_emotion: "",
  tts_tone: "neutral",
  tts_style_prompt: "",

  vad_enabled: true,
  vad_provider: "silero",
  vad_mode: "normal",
  vad_threshold: 0.5,
  vad_min_speech_ms: 250,
  vad_min_silence_ms: 700,
  vad_speech_pad_ms: 100,

  noise_cancellation_enabled: false,
  noise_cancellation_provider: "quail",
};

export const NC_PROVIDERS = [{ value: "quail", label: "Quail" }];
