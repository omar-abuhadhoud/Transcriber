from transcriber.registry import active_engine, get_engine


def run_transcription(audio_path, progress_callback=None, status_callback=None, check_cancel=None):
    get_engine().transcribe(
        audio_path,
        progress_callback=progress_callback,
        status_callback=status_callback,
        check_cancel=check_cancel,
    )


def release_working_memory():
    """Hand back what a run was using, and keep the model where it is.

    Activations, the KV cache and the allocator blocks behind the chunks all go; the
    weights stay in VRAM. This is what a cancel and an emptied queue both want: the
    memory that grows with the work, without paying to load the model again.
    """
    engine = active_engine()
    if engine is not None:
        engine.release_cache()


def release_all_memory():
    """Drop the model too. For shutdown, so VRAM is not held while the app winds down."""
    engine = active_engine()
    if engine is not None:
        engine.unload()
