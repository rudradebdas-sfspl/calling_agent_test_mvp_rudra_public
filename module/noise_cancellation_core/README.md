# noise_cancellation_core

A small, self-contained **noise-cancellation module** with swappable providers,
built exactly like `stt_core` / `tts_core`. Pick a provider by name, and the
matching folder's code is used. Each provider's full implementation lives inside
its own folder under `providers/`, so adding one never touches the others.

Built-in providers:

| Name    | Folder                  | What it does                                  |
|---------|-------------------------|-----------------------------------------------|
| `quail` | `providers/quail/`      | ai-coustics real-time primary-speaker isolation |

---

## 1. File structure

```
noise_cancellation_core/
├── base.py            # NoiseCancellationConfig + BaseNoiseCanceller (the contract)
├── registry.py        # create_provider / from_env / register_provider / list_providers
├── errors.py          # NoiseCancellationError, ProviderNotFound, MissingCredentials
└── providers/
    └── quail/          # <-- ALL Quail code lives here, self-contained
        ├── provider.py # @register_provider("quail") QuailNoiseCanceller
        ├── client.py   # aic_sdk model load (singleton) + Processor
        ├── schemas.py  # HARDCODED model id, tuning defaults, resample helper
        └── errors.py
```

The provider contract (frame-based, streaming — one canceller per call):

```python
canceller.is_active            # bool
canceller.process_frame(frame) # -> list of 0+ enhanced frames ([] while buffering)
canceller.flush()              # -> list of remaining frames (call at end of call)
canceller.stats()              # -> dict
```

---

## 2. Use it (zero config)

The Quail **model id is hardcoded** (`quail-vf-2.1-l-16khz`), so you don't pass
it. The **license is a secret**, so it is read from the environment (or passed
in) — never hardcoded.

```python
from module.noise_cancellation_core.registry import create_provider
from module.noise_cancellation_core.base import NoiseCancellationConfig

# license read from AIC_SDK_LICENSE / QUAIL_SDK_KEY in the environment
nc = create_provider("quail", config=NoiseCancellationConfig(enabled=True))

# in your audio loop:
for enhanced in nc.process_frame(frame):
    ...   # feed enhanced frame to VAD / STT
# at end of call:
for enhanced in nc.flush():
    ...
```

Or pass the license explicitly:
```python
nc = create_provider("quail", license_key="YOUR_KEY",
                   config=NoiseCancellationConfig(enabled=True))
```

Or from the environment helper:
```python
from module.noise_cancellation_core.registry import from_env
nc = from_env("quail")   # reads NC_QUAIL_LICENSE, else the provider's own env keys
```

**Never breaks the call:** if `aic-sdk` isn't installed, or the license/model
fails to load, `is_active` is `False` and `process_frame()` returns the input
frame unchanged (passthrough).

---

## 3. Environment

| Var                   | Required | Meaning                                              |
|-----------------------|----------|------------------------------------------------------|
| `AIC_SDK_LICENSE`     | yes      | Quail SDK license (`QUAIL_SDK_KEY` also accepted)    |
| `ENABLE_QUAIL`        | no       | `false` disables Quail (legacy `ENABLE_DEEPFILTER=false` also works) |
| `QUAIL_MODEL_PATH`    | no       | path to a pre-downloaded `.aicmodel` (skips download)|
| `QUAIL_MODEL_DIR`     | no       | download dir (default `./models`)                    |

`aic-sdk` (import name `aic_sdk`) and `numpy` must be installed.
The model downloads on first load unless `QUAIL_MODEL_PATH` points to a baked file.

---

## 4. Tuning (optional)

Pass a `NoiseCancellationConfig` to adjust behaviour:

| Field               | Default | Meaning                                          |
|---------------------|---------|--------------------------------------------------|
| `enabled`           | True    | turn the denoiser on/off                         |
| `enhancement_level` | 1.0     | 0.0–1.0 strength (best-effort)                   |
| `dry_mix`           | 0.0     | 0.0–0.4 blend back a little raw signal           |
| `min_energy_ratio`  | 0.18    | speech-preservation guardrail                    |
| `energy_floor`      | 0.002   | guardrail energy floor                           |
| `model_id`          | None    | override the hardcoded model id                  |
| `model_path`        | None    | use a pre-downloaded model file                  |

---

## 5. Add another provider (e.g. DeepFilter v3)

Create a new folder — Quail's code is untouched:

```
providers/deepfilter/
├── provider.py   # @register_provider("deepfilter") class DeepFilterCanceller(BaseNoiseCanceller)
├── client.py
├── schemas.py
└── errors.py
```

Then register it in `registry.py`'s `_load_providers()`:
```python
import module.noise_cancellation_core.providers.deepfilter.provider  # noqa: F401
```

Now `create_provider("deepfilter", ...)` works, and selecting "deepfilter" from
the frontend uses that folder's code. Quail and DeepFilter live side by side;
whichever is selected is the one that runs.

---

## 6. Errors

From `noise_cancellation_core.errors`: `ProviderNotFound` (bad name),
`MissingCredentials`, and `NoiseCancellationError` (base). The Quail provider
favours passthrough over raising during a live call.
