"""Speed tiers: user-facing names for how many audio windows go to the GPU at once.

VRAM is what limits this. Measured on a 30 s window (the worst case, since the VAD
caps windows there) the cost is:

    peak VRAM = engine weights + ~0.225 GB per window in the batch

A tier is offered only if it fits the installed GPU with room left for the desktop.
"""

import subprocess
from collections import namedtuple

SpeedTier = namedtuple("SpeedTier", "name label batch_size")
TierStatus = namedtuple("TierStatus", "tier estimate_gb available recommended reason")

SPEED_TIERS = (
    SpeedTier("fast", "Fast", 4),
    SpeedTier("faster", "Faster", 8),
    SpeedTier("turbo", "Turbo", 16),
    SpeedTier("ultra", "Ultra", 24),
)

# Per-window activation cost, measured on 30 s windows for both Qwen engines.
PER_ITEM_GB = 0.225

# Left free for Windows, the desktop and anything else sharing the GPU.
ALLOW_MARGIN_GB = 0.75
# A tier is only marked "recommended" with this much more slack again.
RECOMMEND_MARGIN_GB = 1.5

_total_vram_gb = None


def get_total_vram_gb(refresh=False):
    """Installed VRAM in GB, via nvidia-smi so no CUDA context is created at startup."""
    global _total_vram_gb
    if _total_vram_gb is not None and not refresh:
        return _total_vram_gb

    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        _total_vram_gb = int(result.stdout.strip().splitlines()[0]) / 1024
    except Exception:
        _total_vram_gb = 0.0

    return _total_vram_gb


def estimate_vram_gb(weights_gb, batch_size):
    return weights_gb + PER_ITEM_GB * batch_size


def evaluate_tiers(weights_gb, total_vram_gb=None):
    """Work out which tiers this GPU can run for an engine of the given weight size."""
    if total_vram_gb is None:
        total_vram_gb = get_total_vram_gb()

    statuses = []
    for tier in SPEED_TIERS:
        estimate = estimate_vram_gb(weights_gb, tier.batch_size)

        if not total_vram_gb:
            # No GPU reading available: offer only the smallest tier rather than guess.
            available = tier.batch_size == SPEED_TIERS[0].batch_size
            reason = "" if available else "Could not read GPU memory, so only the smallest tier is offered."
        else:
            available = estimate + ALLOW_MARGIN_GB <= total_vram_gb
            reason = "" if available else (
                f"Needs about {estimate:.1f} GB of VRAM plus headroom. "
                f"This GPU has {total_vram_gb:.1f} GB."
            )

        statuses.append(TierStatus(tier, estimate, available, False, reason))

    # Recommend the largest tier that still leaves comfortable headroom.
    best = None
    for index, status in enumerate(statuses):
        if status.available and status.estimate_gb + RECOMMEND_MARGIN_GB <= (total_vram_gb or 0):
            best = index
    if best is None:
        best = next((i for i, s in enumerate(statuses) if s.available), 0)

    statuses[best] = statuses[best]._replace(recommended=True)
    return statuses


def tier_by_name(name):
    for tier in SPEED_TIERS:
        if tier.name == name:
            return tier
    return None
