"""
Core contracts for noise_cancellation_core.

A noise-cancellation provider takes a `NoiseCancellationConfig` plus its
credentials (e.g. an SDK license) and cleans up a real-time stream of audio
frames — suppressing background noise / other speakers while preserving the
primary speaker's voice for STT.

The interface is frame-based and streaming (one call session = one canceller):
    .is_active            -> bool
    .process_frame(frame) -> list   (0+ enhanced frames; [] while buffering)
    .flush()              -> list   (drain buffered tail at end of call)
    .stats()              -> dict

Nothing here depends on any web framework, database, or this repo.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class NoiseCancellationConfig:
    """Provider-agnostic settings. Each provider uses what it can."""
    enabled: bool = True
    enhancement_level: float = 1.0     # 0.0–1.0 (best-effort)
    dry_mix: float = 0.0               # 0.0–0.4 blend back a little raw signal
    min_energy_ratio: float = 0.18     # speech-preservation guardrail
    energy_floor: float = 0.002
    model_id: Optional[str] = None     # None -> provider's hardcoded default
    model_path: Optional[str] = None   # pre-downloaded model file (skip download)
    model_dir: str = "./models"        # download dir
    # free-form provider-specific overrides
    extra: dict = field(default_factory=dict)


class BaseNoiseCanceller(ABC):
    """
    Base class every provider implements.

    Concrete providers receive their credentials explicitly (license_key / ...)
    so the module stays usable in any project. A provider must NEVER break the
    call: on any failure it should fall back to passing audio through unchanged.
    """

    def __init__(self, config: Optional[NoiseCancellationConfig] = None, **credentials):
        self.config = config or NoiseCancellationConfig()
        self.credentials = credentials

    @property
    @abstractmethod
    def is_active(self) -> bool:
        """True when the provider is loaded and actually enhancing audio."""
        raise NotImplementedError

    @abstractmethod
    def process_frame(self, frame) -> list:
        """
        Process one audio frame. Returns 0+ enhanced frames:
          - buffering         -> []
          - block(s) ready    -> [frame1, frame2, ...]
          - inactive          -> [frame]   (passthrough)
        """
        raise NotImplementedError

    @abstractmethod
    def flush(self) -> list:
        """Process any buffered tail. Call at the end of the call."""
        raise NotImplementedError

    def stats(self) -> dict:
        """Optional runtime stats."""
        return {}
