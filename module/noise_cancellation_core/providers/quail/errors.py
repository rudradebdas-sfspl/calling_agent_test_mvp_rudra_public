"""Quail provider-specific errors (subclass the module's base errors)."""
from module.noise_cancellation_core.errors import NoiseCancellationError


class QuailError(NoiseCancellationError):
    """Quail SDK / model load / processing failure."""
