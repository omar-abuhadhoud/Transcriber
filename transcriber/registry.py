import importlib
import os
from collections import namedtuple

from transcriber.speed import SPEED_TIERS, tier_by_name

# weights_gb is the measured VRAM the loaded weights occupy; the speed picker adds the
# per-window activation cost on top of it to decide which tiers this GPU can run.
EngineSpec = namedtuple("EngineSpec", "module class_name label weights_gb")

DEFAULT_ENGINE = "qwen3-asr-1.7b"
DEFAULT_TIER = "faster"

# Order here is the order shown in the app's engine picker.
ENGINES = {
    "qwen3-asr-1.7b": EngineSpec(
        "transcriber.engines.qwen_asr", "QwenASR17BEngine", "Qwen3-ASR 1.7B", 3.80
    ),
    "qwen3-asr-0.6b": EngineSpec(
        "transcriber.engines.qwen_asr", "QwenASR06BEngine", "Qwen3-ASR 0.6B", 1.46
    ),
}

_active_engine = None
_active_tier = DEFAULT_TIER


def list_engines():
    """(name, label) pairs for the engine picker, without importing any engine."""
    return [(name, spec.label) for name, spec in ENGINES.items()]


def label_for(name):
    spec = ENGINES.get(name)
    return spec.label if spec else name


def name_for_label(label):
    for name, spec in ENGINES.items():
        if spec.label == label:
            return name
    return label


def weights_gb_for(name):
    spec = ENGINES.get(name)
    return spec.weights_gb if spec else 0.0


def active_engine():
    """The loaded engine, or None. Never constructs one, unlike get_engine()."""
    return _active_engine


def active_engine_name():
    if _active_engine is not None:
        return _active_engine.name
    return os.environ.get("TRANSCRIBER_ENGINE") or DEFAULT_ENGINE


def active_tier_name():
    return _active_tier


def set_speed(tier_name):
    """Choose how many windows go to the GPU at once. Applies to the next transcription."""
    global _active_tier

    tier = tier_by_name(tier_name)
    if tier is None:
        available = ", ".join(t.name for t in SPEED_TIERS)
        raise ValueError(f"Unknown speed tier '{tier_name}'. Available: {available}")

    _active_tier = tier.name
    if _active_engine is not None:
        _active_engine.batch_size = tier.batch_size
    return tier


def get_engine(name=None):
    """Return the shared engine instance, importing its module on first use.

    The instance is cached so the loaded model stays in GPU memory across files.
    Called without a name it returns whatever engine is currently selected, so a
    transcription never silently reverts to the default after the user switches.
    """
    global _active_engine

    if name is None:
        if _active_engine is not None:
            return _active_engine
        name = os.environ.get("TRANSCRIBER_ENGINE") or DEFAULT_ENGINE

    requested = name

    if _active_engine is not None and _active_engine.name == requested:
        return _active_engine

    if requested not in ENGINES:
        available = ", ".join(sorted(ENGINES))
        raise ValueError(f"Unknown transcription engine '{requested}'. Available: {available}")

    if _active_engine is not None:
        # Only one model fits in VRAM, so the outgoing engine must let go first.
        _active_engine.unload()
        _active_engine = None

    spec = ENGINES[requested]
    engine_class = getattr(importlib.import_module(spec.module), spec.class_name)
    _active_engine = engine_class()

    tier = tier_by_name(_active_tier)
    if tier is not None:
        _active_engine.batch_size = tier.batch_size

    return _active_engine


def set_engine(name):
    """Switch engines. The new model is not loaded until the next transcription."""
    return get_engine(name)
