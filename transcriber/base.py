import gc
import os
from abc import ABC, abstractmethod

from transcriber.paths import get_model_candidates, get_model_download_dir


class TranscriptionEngine(ABC):
    """Contract every ASR engine implements. The app only ever calls transcribe()."""

    name = ""
    label = ""
    default_model_repo = ""
    required_model_files = ()
    download_patterns = ()
    # Subfolder under models/ holding this engine's weights, so engines never collide.
    model_subdir = ""

    def __init__(self, model_repo=None):
        # No global repo override: with several engines registered, one shared env var
        # would point every engine at the same (wrong) weights.
        self.model_repo = model_repo or self.default_model_repo
        self._model = None

    def has_required_model_files(self, model_dir):
        return all(os.path.exists(os.path.join(model_dir, name)) for name in self.required_model_files)

    def default_model_dir(self):
        base_dir = get_model_download_dir()
        return os.path.join(base_dir, self.model_subdir) if self.model_subdir else base_dir

    def get_model_dir(self):
        for base_dir in get_model_candidates():
            model_dir = os.path.join(base_dir, self.model_subdir) if self.model_subdir else base_dir
            if self.has_required_model_files(model_dir):
                return model_dir
        return self.default_model_dir()

    def ensure_model_downloaded(self, status_callback=None):
        model_dir = self.get_model_dir()
        if self.has_required_model_files(model_dir):
            return model_dir

        download_dir = self.default_model_dir()
        os.makedirs(download_dir, exist_ok=True)

        if status_callback:
            status_callback(f"Downloading model from {self.model_repo}...")

        try:
            from huggingface_hub import snapshot_download

            snapshot_download(
                repo_id=self.model_repo,
                local_dir=download_dir,
                allow_patterns=list(self.download_patterns) or None,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Could not download the model for {self.label or self.name} from {self.model_repo}. "
                "Check the internet connection and try again."
            ) from exc

        return download_dir

    def unload(self):
        """Drop the loaded model so its VRAM is released before another engine loads."""
        self._model = None
        gc.collect()

    def release_cache(self):
        """Hand back working memory while keeping the weights loaded.

        Activations and the KV cache are freed as soon as a run ends, but the allocator
        keeps those blocks reserved, so an idle process can still be holding gigabytes
        the rest of the system cannot use.
        """

    @abstractmethod
    def load(self, status_callback=None):
        """Load the model into memory. Idempotent: repeated calls reuse the loaded model."""

    @abstractmethod
    def transcribe(self, audio_path, progress_callback=None, status_callback=None, check_cancel=None):
        """Transcribe one file.

        progress_callback(fraction, new_text) is called with a 0..1 float and the text
        decoded since the previous call. Engines that cannot report mid-file progress
        may call it once with (1.0, full_text).
        status_callback(message) reports human-readable stage changes.
        check_cancel() is polled between chunks, and by engines that can manage it
        during decoding too; a truthy result aborts the run as soon as it is seen.
        An engine that aborts must release what the run was using (release_cache)
        before it returns, because a cancelled run is exactly when someone is waiting
        for that memory.
        """
