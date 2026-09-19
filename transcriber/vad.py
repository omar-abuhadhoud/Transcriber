"""Silero VAD (v6) over onnxruntime, used to split long audio on silence.

The ONNX weights in assets/ are Silero VAD, MIT licensed:
https://github.com/snakers4/silero-vad
The segmentation logic follows the reference implementation so chunk boundaries stay
consistent with what the model was tuned for.
"""

import os
from dataclasses import dataclass

import numpy as np

WINDOW_SIZE_SAMPLES = 512
ASSET_NAME = "silero_vad_v6.onnx"

_model = None


@dataclass
class VadOptions:
    threshold: float = 0.5
    neg_threshold: float = None
    min_speech_duration_ms: int = 250
    max_speech_duration_s: float = float("inf")
    min_silence_duration_ms: int = 2000
    speech_pad_ms: int = 400


def get_asset_path():
    local = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", ASSET_NAME)
    if os.path.exists(local):
        return local

    # PyInstaller unpacks bundled data next to the executable instead.
    from transcriber.paths import resource_path

    return resource_path(os.path.join("transcriber", "assets", ASSET_NAME))


class SileroVADModel:
    def __init__(self, path):
        import onnxruntime

        opts = onnxruntime.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        opts.enable_cpu_mem_arena = False
        opts.log_severity_level = 4

        self.session = onnxruntime.InferenceSession(
            path,
            providers=["CPUExecutionProvider"],
            sess_options=opts,
        )

    def __call__(self, audio, num_samples=WINDOW_SIZE_SAMPLES, context_size_samples=64):
        assert audio.ndim == 1, "Input should be a 1D array"
        assert audio.shape[0] % num_samples == 0, "Input size should be a multiple of num_samples"

        h = np.zeros((1, 1, 128), dtype="float32")
        c = np.zeros((1, 1, 128), dtype="float32")

        batched_audio = audio.reshape(-1, num_samples)
        context = batched_audio[..., -context_size_samples:]
        context[-1] = 0
        context = np.roll(context, 1, 0)
        batched_audio = np.concatenate([context, batched_audio], 1)
        batched_audio = batched_audio.reshape(-1, num_samples + context_size_samples)

        encoder_batch_size = 10000
        outputs = []
        for start in range(0, batched_audio.shape[0], encoder_batch_size):
            output, h, c = self.session.run(
                None,
                {"input": batched_audio[start:start + encoder_batch_size], "h": h, "c": c},
            )
            outputs.append(output)

        return np.concatenate(outputs, axis=0)


def get_vad_model():
    global _model
    if _model is None:
        _model = SileroVADModel(get_asset_path())
    return _model


def get_speech_timestamps(audio, vad_options=None, sampling_rate=16000, **kwargs):
    """Split audio into speech regions. Returns dicts with 'start'/'end' sample offsets."""
    if vad_options is None:
        vad_options = VadOptions(**kwargs)

    threshold = vad_options.threshold
    neg_threshold = vad_options.neg_threshold
    min_speech_duration_ms = vad_options.min_speech_duration_ms
    max_speech_duration_s = vad_options.max_speech_duration_s
    min_silence_duration_ms = vad_options.min_silence_duration_ms
    speech_pad_ms = vad_options.speech_pad_ms

    min_speech_samples = sampling_rate * min_speech_duration_ms / 1000
    speech_pad_samples = sampling_rate * speech_pad_ms / 1000
    max_speech_samples = (
        sampling_rate * max_speech_duration_s
        - WINDOW_SIZE_SAMPLES
        - 2 * speech_pad_samples
    )
    min_silence_samples = sampling_rate * min_silence_duration_ms / 1000
    min_silence_samples_at_max_speech = sampling_rate * 98 / 1000

    audio_length_samples = len(audio)

    padded_audio = np.pad(
        audio, (0, WINDOW_SIZE_SAMPLES - audio.shape[0] % WINDOW_SIZE_SAMPLES)
    )
    speech_probs = get_vad_model()(padded_audio)

    triggered = False
    speeches = []
    current_speech = {}
    if neg_threshold is None:
        neg_threshold = max(threshold - 0.15, 0.01)

    temp_end = 0
    prev_end = next_start = 0

    for i, speech_prob in enumerate(speech_probs):
        if (speech_prob >= threshold) and temp_end:
            temp_end = 0
            if next_start < prev_end:
                next_start = WINDOW_SIZE_SAMPLES * i

        if (speech_prob >= threshold) and not triggered:
            triggered = True
            current_speech["start"] = WINDOW_SIZE_SAMPLES * i
            continue

        if triggered and (WINDOW_SIZE_SAMPLES * i) - current_speech["start"] > max_speech_samples:
            if prev_end:
                current_speech["end"] = prev_end
                speeches.append(current_speech)
                current_speech = {}
                if next_start < prev_end:
                    triggered = False
                else:
                    current_speech["start"] = next_start
                prev_end = next_start = temp_end = 0
            else:
                current_speech["end"] = WINDOW_SIZE_SAMPLES * i
                speeches.append(current_speech)
                current_speech = {}
                prev_end = next_start = temp_end = 0
                triggered = False
                continue

        if (speech_prob < neg_threshold) and triggered:
            if not temp_end:
                temp_end = WINDOW_SIZE_SAMPLES * i
            if (WINDOW_SIZE_SAMPLES * i) - temp_end > min_silence_samples_at_max_speech:
                prev_end = temp_end
            if (WINDOW_SIZE_SAMPLES * i) - temp_end < min_silence_samples:
                continue

            current_speech["end"] = temp_end
            if (current_speech["end"] - current_speech["start"]) > min_speech_samples:
                speeches.append(current_speech)
            current_speech = {}
            prev_end = next_start = temp_end = 0
            triggered = False
            continue

    if current_speech and (audio_length_samples - current_speech["start"]) > min_speech_samples:
        current_speech["end"] = audio_length_samples
        speeches.append(current_speech)

    for i, speech in enumerate(speeches):
        if i == 0:
            speech["start"] = int(max(0, speech["start"] - speech_pad_samples))
        if i != len(speeches) - 1:
            silence_duration = speeches[i + 1]["start"] - speech["end"]
            if silence_duration < 2 * speech_pad_samples:
                speech["end"] += int(silence_duration // 2)
                speeches[i + 1]["start"] = int(
                    max(0, speeches[i + 1]["start"] - silence_duration // 2)
                )
            else:
                speech["end"] = int(
                    min(audio_length_samples, speech["end"] + speech_pad_samples)
                )
                speeches[i + 1]["start"] = int(
                    max(0, speeches[i + 1]["start"] - speech_pad_samples)
                )
        else:
            speech["end"] = int(min(audio_length_samples, speech["end"] + speech_pad_samples))

    return speeches
