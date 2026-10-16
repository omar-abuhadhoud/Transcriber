import gc
import glob
import os
import re

from transcriber.base import TranscriptionEngine
from transcriber.chunk_log import ChunkLog

SAMPLE_RATE = 16000

# Arabic blocks, Latin, digits and shared punctuation. Anything outside this is a
# decoding artifact (CJK, Cyrillic, ...) rather than speech in this app's languages.
# Ranges are built from codepoints so no invisible character (U+FEFF ends one of these
# blocks) ever sits literally in this file.
_ARABIC_RANGES = (
    (0x0600, 0x06FF),  # Arabic
    (0x0750, 0x077F),  # Arabic Supplement
    (0x08A0, 0x08FF),  # Arabic Extended-A
    (0xFB50, 0xFDFF),  # Arabic Presentation Forms-A
    (0xFE70, 0xFEFF),  # Arabic Presentation Forms-B
)
_ALLOWED_PUNCTUATION = (
    ".,?!:;%&@#-_'\"()[]{}/\\+=*"
    "،؛؟"          # Arabic comma, semicolon, question mark
    "–—‘’“”«»…"
)
_DISALLOWED_CHARS = re.compile(
    "[^"
    + "".join(f"{chr(low)}-{chr(high)}" for low, high in _ARABIC_RANGES)
    + "A-Za-z0-9"
    + r"\s"
    + re.escape(_ALLOWED_PUNCTUATION)
    + "]"
)
_DISALLOWED_RUNS = re.compile(_DISALLOWED_CHARS.pattern + "+")
_WHITESPACE = re.compile(r"\s+")


def _cancel_criteria(check_cancel):
    """Stop generate() at the next decoded token once the run has been cancelled.

    Without this a cancel cannot land until the whole batch has finished decoding:
    up to max_new_tokens of a GPU working on text nobody will read, with every
    window's activations still resident. generate() consults a stopping criterion
    after each token, so the abort costs one decoding step instead of a whole batch.
    """
    if check_cancel is None:
        return None

    import torch
    from transformers import StoppingCriteria, StoppingCriteriaList

    class CancelCriteria(StoppingCriteria):
        def __init__(self):
            self.cancelled = False

        def __call__(self, input_ids, scores, **kwargs):
            if not self.cancelled:
                try:
                    self.cancelled = bool(check_cancel())
                except Exception:
                    # Some callers signal by raising rather than returning True. Either
                    # way it means stop, and letting it out of generate() would pin the
                    # batch's tensors in the traceback of half of transformers.
                    self.cancelled = True
            return torch.full(
                (input_ids.shape[0],),
                self.cancelled,
                dtype=torch.bool,
                device=input_ids.device,
            )

    return StoppingCriteriaList([CancelCriteria()])


class QwenASREngine(TranscriptionEngine):
    """Shared implementation for the Qwen3-ASR family (transformers + torch).

    Qwen3-ASR decodes a whole request in one generate() call, so long files are split
    on silence first and the resulting windows are sent to the GPU in batches. Batching
    is what makes this fast: on one GPU, concurrent threads serialise on the same CUDA
    stream, while a batched generate() actually shares the forward pass.
    """

    # None lets the model detect the language of each window. Forcing "ar" made it
    # translate English speech instead of transcribing it, and the translation could
    # drift into Chinese, which _clean then deleted: whole sentences vanished.
    language = None
    # Window lengths: never cut before min_chunk_seconds, always cut at chunk_seconds.
    min_chunk_seconds = 15
    chunk_seconds = 30
    # (window length in seconds, pause in ms): once a window is that long, the first
    # pause at least that long ends it. Steps must be in ascending order.
    pause_steps = ((0, 350), (20, 200), (25, 100))
    # Silero speech probability: a frame below silence_threshold counts towards a
    # pause, and a window with no frame at speech_threshold is not sent at all.
    silence_threshold = 0.35
    speech_threshold = 0.5
    # Every window after the first starts this much earlier in the real audio, reaching
    # back into the pause the cut was made in. A window that opens on the very first
    # sample of a word tends to lose that word's first letter; this lead-in is the
    # file's own audio, so nothing is synthesised and nothing before the word is lost.
    lead_in_ms = 50
    max_new_tokens = 440
    # Default only; the app overrides this from the selected speed tier.
    batch_size = 4
    dtype_name = "float16"
    # The app transcribes Arabic and English only, so any other script in the output is
    # removed: either a hallucination or speech in a language the app does not serve.
    strip_foreign_scripts = True

    def has_required_model_files(self, model_dir):
        if not os.path.isfile(os.path.join(model_dir, "config.json")):
            return False
        return bool(glob.glob(os.path.join(model_dir, "*.safetensors")))

    def load(self, status_callback=None):
        if self._model is not None:
            return self._model

        if status_callback: status_callback("Checking transcription model...")
        model_dir = self.ensure_model_downloaded(status_callback)

        if status_callback: status_callback("Loading model into GPU memory...")

        import torch
        from transformers import AutoModelForMultimodalLM, AutoProcessor

        processor = AutoProcessor.from_pretrained(model_dir)

        # A rate mismatch would not raise, it would just yield garbage transcripts.
        model_rate = processor.feature_extractor.sampling_rate
        if model_rate != SAMPLE_RATE:
            raise ValueError(
                f"{self.label} expects {model_rate} Hz audio but this engine decodes at "
                f"{SAMPLE_RATE} Hz. Update SAMPLE_RATE in transcriber/engines/qwen_asr.py."
            )

        model = AutoModelForMultimodalLM.from_pretrained(
            model_dir,
            dtype=getattr(torch, self.dtype_name),
        )
        model.to("cuda")
        model.eval()

        self._model = (model, processor)
        return self._model

    def unload(self):
        super().unload()
        self.release_cache()

    def release_cache(self):
        try:
            import torch
        except ImportError:
            return
        # Tensors dropped a moment ago can still be held by a reference cycle, and the
        # allocator cannot hand a block back while anything at all points at it.
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    def transcribe(self, audio_path, progress_callback=None, status_callback=None, check_cancel=None):
        model, processor = self.load(status_callback)

        if status_callback: status_callback(f"Transcribing {os.path.basename(audio_path)}...")

        from transcriber.audio import decode_audio

        audio = decode_audio(audio_path, sampling_rate=SAMPLE_RATE)
        total_samples = len(audio)
        if total_samples == 0:
            return

        if check_cancel and check_cancel():
            return

        windows, reasons = self._split_on_silence(audio)
        log = ChunkLog(
            audio_path, total_samples, SAMPLE_RATE, windows, self.batch_size, self.lead_in_ms
        )

        # Set the moment anything abandons the run, so the way out can drop the
        # decoded audio and the blocks the batches were using instead of leaving an
        # idle process holding them.
        cancelled = False
        try:
            for index in range(0, len(windows), self.batch_size):
                if check_cancel and check_cancel():
                    cancelled = True
                    return

                group = windows[index:index + self.batch_size]
                log.batch_started()
                texts = self._transcribe_batch(
                    model, processor, [self._window_audio(audio, s, e) for s, e in group], check_cancel
                )
                removed = [self._foreign_text(text) for text in texts]
                texts = [self._clean(text) for text in texts]
                log.batch_finished(
                    index // self.batch_size + 1,
                    group,
                    index + 1,
                    reasons[index:index + self.batch_size],
                    texts,
                    removed,
                )

                # A cancel lands inside generate(), which then returns whatever it had
                # decoded so far. That text belongs to a run nobody is waiting for.
                if check_cancel and check_cancel():
                    cancelled = True
                    return

                # Emitted in window order, so the recovery file stays in sync with the audio.
                for (_, end), text in zip(group, texts):
                    if progress_callback and text:
                        progress_callback(min(1.0, end / total_samples), text)
        except BaseException:
            # Callers may signal a cancel by raising out of one of the callbacks.
            cancelled = True
            raise
        finally:
            log.close("Cancelled" if cancelled else "Finished")
            if cancelled:
                audio = windows = reasons = None
                self.release_cache()

        if status_callback: status_callback("Done!")

    def _window_audio(self, audio, start, end):
        """The window's samples, reaching lead_in_ms back into the audio before it."""
        lead_in = self.lead_in_ms * SAMPLE_RATE // 1000
        return audio[max(0, start - lead_in):end]

    def _pause_step(self, chunk_seconds):
        """The (from seconds, pause ms) step that applies to a chunk this long."""
        current = self.pause_steps[0]
        for step in self.pause_steps:
            if chunk_seconds >= step[0]:
                current = step
        return current

    def _split_on_silence(self, audio):
        """Cut the audio into windows at pauses that get shorter as the window grows.

        Walking Silero's 32 ms frames from the start of the current window: nothing is
        cut before min_chunk_seconds; after that the first pause of pause_steps' length
        for the window's current size ends it; at chunk_seconds it is cut regardless.
        The cut is made once the pause has lasted that long, so the pause's remainder
        opens the next window. Windows are back to back and no audio is dropped, except
        a window in which VAD heard no speech at all.

        Returns the (start, end) windows and, alongside them, why each one ends where
        it does.
        """
        import numpy as np

        from transcriber.vad import WINDOW_SIZE_SAMPLES, get_vad_model

        total = len(audio)
        padded = np.pad(audio, (0, WINDOW_SIZE_SAMPLES - total % WINDOW_SIZE_SAMPLES))
        probs = get_vad_model()(padded)

        frame_ms = WINDOW_SIZE_SAMPLES * 1000 / SAMPLE_RATE
        min_frames = int(self.min_chunk_seconds * 1000 / frame_ms)
        max_frames = int(self.chunk_seconds * 1000 / frame_ms)

        windows = []
        reasons = []
        start = 0
        silent_run = 0
        heard_speech = False

        def close(end_frame, reason):
            if heard_speech:
                windows.append((start * WINDOW_SIZE_SAMPLES, min(end_frame * WINDOW_SIZE_SAMPLES, total)))
                reasons.append(reason)

        for frame, prob in enumerate(probs):
            heard_speech = heard_speech or prob >= self.speech_threshold
            silent_run = silent_run + 1 if prob < self.silence_threshold else 0
            length = frame + 1 - start

            if length >= max_frames:
                reason = f"no pause before {self.chunk_seconds} s; forced cut"
            elif length >= min_frames:
                from_seconds, needed = self._pause_step(length * frame_ms / 1000)
                if silent_run * frame_ms < needed:
                    continue
                reason = (
                    f"first {needed} ms pause "
                    f"(chunk past {max(from_seconds, self.min_chunk_seconds)} s)"
                )
            else:
                continue

            close(frame + 1, reason)
            start = frame + 1
            silent_run = 0
            heard_speech = False

        if start * WINDOW_SIZE_SAMPLES < total:
            close(len(probs), "end of audio")

        if not windows:
            return [(0, total)], ["no speech detected; whole file sent as one chunk"]
        return windows, reasons

    def _transcribe_batch(self, model, processor, chunks, check_cancel=None):
        import torch

        try:
            return self._generate(model, processor, chunks, check_cancel)
        except torch.cuda.OutOfMemoryError:
            if len(chunks) == 1:
                raise
            # Consumer GPUs share VRAM with the desktop, so headroom moves at runtime.
            torch.cuda.empty_cache()
            middle = len(chunks) // 2
            return (
                self._transcribe_batch(model, processor, chunks[:middle], check_cancel)
                + self._transcribe_batch(model, processor, chunks[middle:], check_cancel)
            )

    def _generate(self, model, processor, chunks, check_cancel=None):
        import torch

        inputs = processor.apply_transcription_request(
            audio=chunks,
            language=self.language,
        ).to(model.device, model.dtype)

        output_ids = None
        try:
            with torch.inference_mode():
                output_ids = model.generate(
                    **inputs,
                    max_new_tokens=self.max_new_tokens,
                    stopping_criteria=_cancel_criteria(check_cancel),
                )

            if check_cancel and check_cancel():
                return []

            prompt_length = inputs["input_ids"].shape[1]
            return [
                processor.decode(output_ids[row, prompt_length:], return_format="transcription_only")
                for row in range(output_ids.shape[0])
            ]
        finally:
            # Dropped here, in the frame that owns them. On the way out of a cancel an
            # exception is usually in flight, and its traceback keeps every frame it
            # passed through alive -- including this one, and with it the whole batch's
            # activations, which is exactly the VRAM the cancel is meant to give back.
            del inputs, output_ids

    def _foreign_text(self, text):
        """The stretches _clean is about to drop, so the dev log can say what was lost."""
        if not self.strip_foreign_scripts:
            return ""
        return " ... ".join(_DISALLOWED_RUNS.findall(text))

    def _clean(self, text):
        text = text.strip()
        if self.strip_foreign_scripts:
            text = _DISALLOWED_CHARS.sub("", text)
        return _WHITESPACE.sub(" ", text).strip()


class QwenASR17BEngine(QwenASREngine):
    name = "qwen3-asr-1.7b"
    label = "Qwen3-ASR 1.7B"
    default_model_repo = "Qwen/Qwen3-ASR-1.7B-hf"
    model_subdir = "qwen3-asr-1.7b"


class QwenASR06BEngine(QwenASREngine):
    name = "qwen3-asr-0.6b"
    label = "Qwen3-ASR 0.6B"
    default_model_repo = "Qwen/Qwen3-ASR-0.6B-hf"
    model_subdir = "qwen3-asr-0.6b"
