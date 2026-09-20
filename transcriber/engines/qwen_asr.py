import gc
import glob
import os
import re

from transcriber.base import TranscriptionEngine

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

    language = "ar"
    chunk_seconds = 30
    max_new_tokens = 440
    # Default only; the app overrides this from the selected speed tier.
    batch_size = 4
    dtype_name = "float16"
    # Forcing language="ar" keeps English terms in Latin script (verified), so this only
    # removes hallucinated scripts, never legitimate Arabic/English code-switching.
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

        windows = self._split_on_silence(audio)

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
                texts = self._transcribe_batch(
                    model, processor, [audio[s:e] for s, e in group], check_cancel
                )

                # A cancel lands inside generate(), which then returns whatever it had
                # decoded so far. That text belongs to a run nobody is waiting for.
                if check_cancel and check_cancel():
                    cancelled = True
                    return

                # Emitted in window order, so the recovery file stays in sync with the audio.
                for (_, end), text in zip(group, texts):
                    text = self._clean(text)
                    if progress_callback and text:
                        progress_callback(min(1.0, end / total_samples), text)
        except BaseException:
            # Callers may signal a cancel by raising out of one of the callbacks.
            cancelled = True
            raise
        finally:
            if cancelled:
                audio = windows = None
                self.release_cache()

        if status_callback: status_callback("Done!")

    def _split_on_silence(self, audio):
        """Group VAD speech regions into windows of at most chunk_seconds."""
        from transcriber.vad import VadOptions, get_speech_timestamps

        options = VadOptions(
            max_speech_duration_s=self.chunk_seconds,
            min_silence_duration_ms=500,
        )
        speech = get_speech_timestamps(audio, options, sampling_rate=SAMPLE_RATE)

        if not speech:
            return [(0, len(audio))]

        max_samples = self.chunk_seconds * SAMPLE_RATE
        windows = []
        start = speech[0]["start"]
        end = speech[0]["end"]

        for region in speech[1:]:
            if region["end"] - start <= max_samples:
                end = region["end"]
            else:
                windows.append((start, end))
                start = region["start"]
                end = region["end"]

        windows.append((start, end))
        return windows

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
