"""Development-only log of how a run was chunked and batched.

Each transcription gets its own file under logs/ at the project root, listing every
batch with its windows: where each one starts and ends in the audio, how long it is,
why it was cut there, how long the GPU took on it and the text it produced. Nothing is
written by a frozen (installed) build.

A batch is decoded in one generate() call, so its windows finish together: the time
shown for a window is the wall time of the batch it was decoded in.
"""

import os
import sys
import time
import uuid
from datetime import datetime

from transcriber.paths import get_install_root


def _enabled():
    return not getattr(sys, "frozen", False)


def _mmss(seconds):
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes:02d}:{secs:02d}"


def _mmssms(seconds):
    millis = int(round(seconds * 1000))
    minutes, millis = divmod(millis, 60000)
    secs, millis = divmod(millis, 1000)
    return f"{minutes:02d}:{secs:02d}:{millis:03d}"


class ChunkLog:
    """Writes one run's log as it goes, so a crash or cancel still leaves what happened."""

    def __init__(self, audio_path, total_samples, sample_rate, windows, batch_size, lead_in_ms=0,
                 artifact_callback=None):
        self.file = None
        self.sample_rate = sample_rate
        self.run_started = time.perf_counter()
        if not _enabled():
            return

        try:
            folder = os.path.join(get_install_root(), "logs")
            os.makedirs(folder, exist_ok=True)
            name = os.path.splitext(os.path.basename(audio_path))[0]
            stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            path = os.path.join(folder, f"{stamp}_{name}_{uuid.uuid4().hex[:8]}.log")
            self.file = open(path, "w", encoding="utf-8")
            if artifact_callback:
                artifact_callback(path)
        except OSError:
            self.file = None
            return

        batches = (len(windows) + batch_size - 1) // batch_size
        self._write(
            f"File:       {os.path.basename(audio_path)}\n"
            f"Started:    {datetime.now():%Y-%m-%d %H:%M:%S}\n"
            f"Duration:   {_mmss(total_samples / sample_rate)}\n"
            f"Chunks:     {len(windows)}\n"
            f"Batch size: {batch_size}\n"
            f"Batches:    {batches}\n"
            f"Lead-in:    each chunk after the first also gets the {lead_in_ms} ms of real "
            f"audio before its start (times below are the cut points, without it)\n"
        )

    def batch_started(self):
        self.batch_started_at = time.perf_counter()

    def batch_finished(self, number, group, first_chunk_number, reasons, texts, removed):
        if self.file is None:
            return
        elapsed = time.perf_counter() - self.batch_started_at
        lines = [f"\nBatch {number}  ({len(group)} chunks, processed in {elapsed:.1f} s)\n"]
        for offset, (start, end) in enumerate(group):
            start_s = start / self.sample_rate
            end_s = end / self.sample_rate
            # A cancel mid-batch hands back no text at all.
            text = texts[offset] if offset < len(texts) else ""
            lines.append(
                f"  Chunk {first_chunk_number + offset:<4} "
                f"{_mmssms(start_s)} -> {_mmssms(end_s)}   "
                f"duration {end_s - start_s:6.3f} s   "
                f"processed in {elapsed:.1f} s\n"
                f"             Split: {reasons[offset]}\n"
                f"             Text:  {text or '(no text)'}\n"
            )
            dropped = removed[offset] if offset < len(removed) else ""
            if dropped:
                if len(dropped) > 300:
                    dropped = dropped[:300] + " ..."
                lines.append(
                    f"             ERROR: truncated text because a language other than "
                    f"Arabic and English appeared ({len(removed[offset])} chars removed)\n"
                    f"             Removed: {dropped}\n"
                )
        self._write("".join(lines))

    def close(self, outcome):
        if self.file is None:
            return
        total = time.perf_counter() - self.run_started
        self._write(f"\n{outcome} after {total:.1f} s\n")
        try:
            self.file.close()
        except OSError:
            pass
        self.file = None

    def _write(self, text):
        # A log that cannot be written must never cost the user their transcript.
        try:
            self.file.write(text)
            self.file.flush()
        except (OSError, ValueError):
            try:
                self.file.close()
            except OSError:
                pass
            self.file = None
