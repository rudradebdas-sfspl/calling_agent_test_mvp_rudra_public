"""
Noise-cancellation adapter.

The ONLY place that knows about both the app (agent ORM rows, .env) and the
module.noise_cancellation_core package. It maps an agent's stored settings + the
server's license onto the module, then returns a ready canceller (or None when
disabled).

The worker uses the returned object's process_frame()/flush()/is_active exactly
as the standalone module defines them.
"""
from typing import Optional

from module.noise_cancellation_core.base import BaseNoiseCanceller, NoiseCancellationConfig
from module.noise_cancellation_core.registry import create_provider

from backend.config import settings


def _credentials_for(provider: str) -> dict:
    if provider == "quail":
        # license is optional here — the provider also reads AIC_SDK_LICENSE itself
        return {"license_key": settings.AIC_SDK_LICENSE or settings.QUAIL_SDK_KEY or None}
    return {}


def build_noise_canceller(agent) -> Optional[BaseNoiseCanceller]:
    """
    Return a ready canceller for the agent, or None when noise cancellation is
    disabled for this agent (so the worker simply passes audio straight through).
    """
    if not getattr(agent, "noise_cancellation_enabled", False):
        return None

    provider = getattr(agent, "noise_cancellation_provider", None) or "quail"
    config = NoiseCancellationConfig(enabled=True)
    try:
        return create_provider(provider, config=config, **_credentials_for(provider))
    except Exception:
        # Never let denoiser setup break a call — fall back to passthrough.
        return None
