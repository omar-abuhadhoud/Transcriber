"""Audio decoding with PyAV, which bundles FFmpeg so nothing has to be installed system-wide."""

import gc
import io
import itertools

import av
import numpy as np


def decode_audio(input_file, sampling_rate=16000):
    """Decode any container PyAV can read into a mono float32 array at sampling_rate."""
    resampler = av.audio.resampler.AudioResampler(
        format="s16",
        layout="mono",
        rate=sampling_rate,
    )

    raw_buffer = io.BytesIO()

    with av.open(input_file, mode="r", metadata_errors="ignore") as container:
        frames = container.decode(audio=0)
        frames = _ignore_invalid_frames(frames)
        frames = _group_frames(frames, 500000)
        frames = _resample_frames(frames, resampler)

        for frame in frames:
            raw_buffer.write(frame.to_ndarray())

    # PyAV holds internal references to the resampler that only a manual collection frees.
    del resampler
    gc.collect()

    samples = np.frombuffer(raw_buffer.getbuffer(), dtype=np.int16)
    return samples.astype(np.float32) / 32768.0


def _ignore_invalid_frames(frames):
    iterator = iter(frames)
    while True:
        try:
            yield next(iterator)
        except StopIteration:
            break
        except av.error.InvalidDataError:
            continue


def _group_frames(frames, num_samples=None):
    fifo = av.audio.fifo.AudioFifo()

    for frame in frames:
        frame.pts = None
        fifo.write(frame)

        if num_samples is not None and fifo.samples >= num_samples:
            yield fifo.read()

    if fifo.samples > 0:
        yield fifo.read()


def _resample_frames(frames, resampler):
    # A None frame flushes whatever the resampler is still holding.
    for frame in itertools.chain(frames, [None]):
        yield from resampler.resample(frame)
