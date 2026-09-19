from transcriber.registry import active_engine, get_engine


def run_transcription(audio_path, progress_callback=None, status_callback=None, check_cancel=None):
    get_engine().transcribe(
        audio_path,
        progress_callback=progress_callback,
        status_callback=status_callback,
        check_cancel=check_cancel,
    )


def release_idle_memory():
    """Return working VRAM to the system once the queue is empty. Keeps the model loaded."""
    engine = active_engine()
    if engine is not None:
        engine.release_cache()


def release_all_memory():
    """Drop the model too. For shutdown, so VRAM is not held while the app winds down."""
    engine = active_engine()
    if engine is not None:
        engine.unload()
