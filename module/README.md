# module/

এই folder-এ দুটো reusable Python module আছে:

| Module | কাজ |
|--------|-----|
| `stt_core` | Speech-to-Text (Deepgram, Sarvam) |
| `tts_core` | Text-to-Speech (Cartesia, Sarvam) |

কোনো `pip install` লাগবে না — সরাসরি import করা যাবে।

---

## Structure

```
module/                              ← plain directory (কোনো __init__.py নেই)
  stt_core/                          ← plain directory
    base.py                          ← STTConfig, STTResult, BaseSTTProvider
    registry.py                      ← create_provider, list_providers, register_provider
    audio.py                         ← pcm_to_wav helper
    errors.py                        ← STTError, MissingCredentials, ...
    providers/
      deepgram/
        provider.py                  ← DeepgramSTTProvider  (model: nova-3)
        client.py                    ← HTTP client
        schemas.py                   ← request builders
        errors.py                    ← DeepgramSTTError
      sarvam/
        provider.py                  ← SarvamSTTProvider  (model: Sarvam API default)
        client.py                    ← HTTP client
        schemas.py                   ← request builders
        errors.py                    ← SarvamSTTError
  tts_core/                          ← plain directory
    base.py                          ← TTSConfig, OutputFormat, BaseTTSProvider
    registry.py                      ← create_provider, list_providers, register_provider
    errors.py                        ← TTSError, MissingCredentials, ...
    providers/
      cartesia/
        provider.py                  ← CartesiaTTSProvider  (model: sonic-3)
        client.py                    ← HTTP streaming client
        mapper.py                    ← tone mapping + voice ID resolution
        schemas.py                   ← request builders
        errors.py                    ← CartesiaError, CartesiaVoiceConfigError
      sarvam/
        provider.py                  ← SarvamTTSProvider  (model: bulbul:v2)
        client.py                    ← HTTP client
        mapper.py                    ← language code mapping
        schemas.py                   ← request builders
        errors.py                    ← SarvamTTSError
```

---

## অন্য Project-এ Share / Copy করার নিয়ম

**Step 1 — folder copy করো (folder-এর নাম `module` রাখতে হবে):**
```
their_project/
  module/          ← এই folder টা হুবহু copy করে দাও
    stt_core/
    tts_core/
  their_code.py
```

> ⚠️ folder rename করা যাবে না — ভেতরে সব import `module.xxx` হিসেবে hardcoded আছে।
> নাম বদলালে সব import ভেঙে যাবে।

**Step 2 — একটাই dependency install করো:**
```bash
pip install httpx
```

> `httpx` হলো HTTP client library — এটা দিয়ে Cartesia / Sarvam / Deepgram-এর
> API-তে request পাঠানো হয়। এছাড়া আর কোনো library লাগবে না।

**Step 3 — সরাসরি import করো:**
```python
from module.tts_core.base import TTSConfig
from module.tts_core.registry import create_provider

from module.stt_core.base import STTConfig
from module.stt_core.registry import create_provider
```

---

## Hardcoded Models

| Module | Provider | Model |
|--------|----------|-------|
| `tts_core` | Cartesia | `sonic-3` |
| `tts_core` | Sarvam | `bulbul:v2` |
| `stt_core` | Deepgram | `nova-3` |
| `stt_core` | Sarvam | *(Sarvam API default)* |

---

## TTS — `module/tts_core`

### Cartesia (streaming PCM)

```python
from module.tts_core.base import TTSConfig
from module.tts_core.registry import create_provider

tts = create_provider(
    "cartesia",
    api_key="sk-...",                          # CARTESIA_API_KEY
    config=TTSConfig(
        voice_id="abc123",                     # optional — env fallback by language
        language="bn-IN",                      # "en", "hi", "bn", "bn-IN", etc.
        tone="friendly",                       # neutral / professional / friendly /
                                               # calm / energetic / empathetic /
                                               # serious / support-agent / sales-agent / custom
        speed=1.0,                             # 0.5 – 2.0
        sample_rate=24000,
    ),
)

# Streaming (returns raw PCM s16le chunks)
async for chunk in tts.synthesize("Hello!"):
    audio_buffer.write(chunk)

# One-shot (collect all chunks)
pcm_bytes = await tts.synthesize_all("Hello!")
```

**Voice ID resolution (Cartesia)** — priority order:
1. `config.voice_id` — code থেকে দেওয়া
2. `config.extra["voice_id"]` — advanced override
3. Language-based env var:
   - Bengali → `CARTESIA_BENGALI_VOICE_ID`
   - Hindi → `CARTESIA_HINDI_VOICE_ID`
   - English → `CARTESIA_ENGLISH_VOICE_ID`

---

### Sarvam (WAV chunks)

```python
from module.tts_core.base import TTSConfig
from module.tts_core.registry import create_provider

tts = create_provider(
    "sarvam",
    api_key="sk-...",                          # SARVAM_API_KEY
    config=TTSConfig(
        voice_id="manisha",                    # Sarvam speaker name (optional)
        language="bn-IN",
        speed=1.0,
        pitch=0.0,
        volume=1.0,
        sample_rate=8000,                      # Sarvam telephony: 8000
    ),
)

async for chunk in tts.synthesize("হ্যালো!"):
    audio_buffer.write(chunk)                  # WAV chunks
```

---

### Available TTS Providers

```python
from module.tts_core.registry import list_providers
print(list_providers())   # ['cartesia', 'sarvam']
```

---

## STT — `module/stt_core`

### Deepgram (model hardcoded: `nova-3`)

```python
from module.stt_core.base import STTConfig
from module.stt_core.registry import create_provider

stt = create_provider(
    "deepgram",
    api_key="...",                             # DEEPGRAM_API_KEY
    config=STTConfig(
        language_code="en-IN",                 # BCP-47 language code
        auto_language_detection=False,         # True হলে language_code ignore হবে
    ),
)

result = await stt.transcribe(pcm_bytes, sample_rate=16000)
print(result.text)        # transcribed text
print(result.language)    # detected / requested language
```

---

### Sarvam

```python
from module.stt_core.base import STTConfig
from module.stt_core.registry import create_provider

stt = create_provider(
    "sarvam",
    api_key="...",                             # SARVAM_API_KEY
    config=STTConfig(
        language_code="bn-IN",
        auto_language_detection=False,         # True হলে Sarvam "unknown" পাঠায়
    ),
)

result = await stt.transcribe(pcm_bytes, sample_rate=16000)
print(result.text)
```

> Input audio: raw 16-bit PCM। Module ভেতরে WAV-এ convert করে Sarvam-এ পাঠায়।

---

### Available STT Providers

```python
from module.stt_core.registry import list_providers
print(list_providers())   # ['deepgram', 'sarvam']
```

---

## TTSConfig Fields

| Field | Type | Default | বিবরণ |
|-------|------|---------|-------|
| `voice_id` | `str \| None` | `None` | Provider-specific voice ID |
| `language` | `str` | `"en"` | Language code |
| `speed` | `float` | `1.0` | 0.5 (slow) – 2.0 (fast) |
| `pitch` | `float` | `0.0` | Pitch adjustment |
| `volume` | `float` | `1.0` | Volume / loudness |
| `emotion` | `str \| None` | `None` | Cartesia emotion tag |
| `tone` | `str` | `"neutral"` | Tone preset (Cartesia only) |
| `style_prompt` | `str \| None` | `None` | Custom style instruction (`tone="custom"` এ) |
| `sample_rate` | `int` | `24000` | Output audio sample rate |

---

## STTConfig Fields

| Field | Type | Default | বিবরণ |
|-------|------|---------|-------|
| `language_code` | `str` | `""` | BCP-47 code, e.g. `"bn-IN"`, `"en-IN"` |
| `auto_language_detection` | `bool` | `False` | Provider-এর auto detect চালু করে |

---

## নতুন Provider যোগ করা

### TTS provider add:

1. `module/tts_core/providers/<name>/` folder বানাও
2. `provider.py`-তে `@register_provider("<name>")` দিয়ে `BaseTTSProvider` extend করো:
   ```python
   from module.tts_core.base import BaseTTSProvider, TTSConfig
   from module.tts_core.registry import register_provider

   @register_provider("<name>")
   class MyTTSProvider(BaseTTSProvider):
       ...
   ```
3. `module/tts_core/registry.py` এর `_load_providers()` function-এ import যোগ করো:
   ```python
   def _load_providers():
       if not _REGISTRY:
           import module.tts_core.providers.cartesia.provider  # noqa
           import module.tts_core.providers.sarvam.provider    # noqa
           import module.tts_core.providers.<name>.provider    # noqa  ← এটা যোগ করো
   ```

### STT provider add:

1. `module/stt_core/providers/<name>/` folder বানাও
2. `provider.py`-তে `@register_provider("<name>")` দিয়ে `BaseSTTProvider` extend করো:
   ```python
   from module.stt_core.base import BaseSTTProvider, STTConfig, STTResult
   from module.stt_core.registry import register_provider

   @register_provider("<name>")
   class MySTTProvider(BaseSTTProvider):
       ...
   ```
3. `module/stt_core/registry.py` এর `_load_providers()` function-এ import যোগ করো:
   ```python
   def _load_providers():
       if not _REGISTRY:
           import module.stt_core.providers.deepgram.provider  # noqa
           import module.stt_core.providers.sarvam.provider    # noqa
           import module.stt_core.providers.<name>.provider    # noqa  ← এটা যোগ করো
   ```

> Provider গুলো **lazy load** হয় — প্রথমবার `create_provider()` বা `list_providers()` call করলে
> তখনই automatically register হয়। আলাদা করে import করতে হয় না।

---

## Backend-এ কিভাবে Connected

```
module/stt_core/registry.py  ←──  backend/services/stt/factory.py  ←──  agent_worker.py
module/tts_core/registry.py  ←──  backend/services/tts/factory.py  ←──  agent_worker.py
```

```python
# backend/services/stt/factory.py
from module.stt_core.base import STTConfig, BaseSTTProvider
from module.stt_core.registry import create_provider

# backend/services/tts/factory.py
from module.tts_core.base import TTSConfig, BaseTTSProvider
from module.tts_core.registry import create_provider
```

Factory শুধু `.env` থেকে `api_key` নেয় এবং agent-এর language / voice / tone
settings দিয়ে `create_provider(...)` call করে। Model সব সময় hardcoded।


# Sarvam Bulbul v3 — Wiring Guide

Drop the attached `sarvam_v3/` folder into your existing project at:

```
module/tts_core/providers/sarvam_v3/
```

(same level as your existing `cartesia/` and `sarvam/` provider folders)

Then make these exact edits in your existing files.

---

## 1. `module/tts_core/registry.py`

Find `_load_providers()` and add one line:

```python
def _load_providers():
    """Lazily import providers so they register themselves."""
    if not _REGISTRY:
        import module.tts_core.providers.cartesia.provider  # noqa: F401
        import module.tts_core.providers.sarvam.provider    # noqa: F401
        import module.tts_core.providers.sarvam_v3.provider # noqa: F401   ← ADD THIS
```

---

## 2. `backend/config.py`

Add inside your `Settings` class:

```python
    SARVAM_V3_DEFAULT_SPEAKER: str = "shubh"
    SARVAM_V3_TEMPERATURE: float = 0.6
    SARVAM_V3_USE_WEBSOCKET: bool = True
```

---

## 3. `backend/services/tts/factory.py`

In `_credentials_for()`, add a branch:

```python
def _credentials_for(provider: str) -> dict:
    if provider == "cartesia":
        return {"api_key": settings.CARTESIA_API_KEY}
    if provider == "sarvam":
        return {"api_key": settings.SARVAM_API_KEY}
    if provider == "sarvam-v3":                              # ← ADD THIS BLOCK
        return {
            "api_key": settings.SARVAM_API_KEY,
            "temperature": settings.SARVAM_V3_TEMPERATURE,
            "use_websocket": settings.SARVAM_V3_USE_WEBSOCKET,
        }
    raise ValueError(f"Unknown tts_provider: {provider}")
```

In `_saved_voice_id()`, add a branch:

```python
def _saved_voice_id(provider: str, agent) -> str | None:
    if provider == "cartesia":
        return agent.cartesia_voice_id or None
    if provider == "sarvam":
        return agent.cartesia_voice_id or settings.SARVAM_TTS_DEFAULT_SPEAKER or None
    if provider == "sarvam-v3":                              # ← ADD THIS BLOCK
        return agent.cartesia_voice_id or settings.SARVAM_V3_DEFAULT_SPEAKER or None
    return None
```

In `_sample_rate_for()`, sarvam-v3 falls through to the existing default
(24000) — only add a comment if you want, no code change strictly needed:

```python
def _sample_rate_for(provider: str) -> int:
    if provider == "sarvam":
        return settings.TTS_SAMPLE_RATE
    # sarvam-v3 and cartesia both default to 24kHz
    return 24000
```

---

## 4. `backend/schemas/agent.py`

Add `"sarvam-v3"` to your supported-providers set:

```python
SUPPORTED_TTS_PROVIDERS = {"cartesia", "sarvam", "sarvam-v3"}   # ← add sarvam-v3
```

---

## 5. `backend/api/providers.py`

Add a label and capability entry:

```python
_LABELS = {
    "cartesia": "Cartesia",
    "sarvam": "Sarvam (v2)",
    "sarvam-v3": "Sarvam Bulbul v3",                          # ← ADD THIS
    "deepgram": "Deepgram",
}

_TTS_CAPS = {
    ...,  # your existing entries
    "sarvam-v3": {                                            # ← ADD THIS BLOCK
        "supports_streaming": True,
        "supports_voice_id": True,
        "supports_tone": False,
        "supports_speed": True,
        "supports_pitch": False,
        "default_sample_rate": 24000,
        "voice_id_optional": True,
        "voice_id_fallback": "default_shubh",
    },
}
```

---

## 6. Frontend dropdown — `frontend/src/constants/agentOptions.js`

```js
export const TTS_PROVIDERS = [
  { value: "cartesia", label: "Cartesia" },
  { value: "sarvam", label: "Sarvam (v2)" },
  { value: "sarvam-v3", label: "Sarvam Bulbul v3" },   // ← ADD THIS
];
```

---

## 7. `.env`

Add these (reuses the existing `SARVAM_API_KEY` — no new key needed):

```bash
SARVAM_V3_DEFAULT_SPEAKER=shubh
SARVAM_V3_TEMPERATURE=0.6
SARVAM_V3_USE_WEBSOCKET=true
```

---

## 8. `requirements.txt`

Add:

```
sarvamai==0.1.28
```

(`httpx` is already a dependency for the other providers — no change needed
there.)

---

That's all 8 edits. Nothing else needs to change — `agent_worker.py`, RAG,
VAD, LLM, Cartesia, and Sarvam v2 are untouched by this integration.
