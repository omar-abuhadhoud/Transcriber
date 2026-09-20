"""Runs downloads in parallel, off the UI thread and away from the GPU.

Downloads are network work. They spend their time waiting on sockets, they never
import torch and they never open a CUDA context, so they cannot contend with a
transcription for VRAM -- the one thing in this app that must not be shared. They are
threads rather than processes because a thread that is blocked on a socket holds no
GIL, and four extra interpreters would cost a second of startup each and a pipe to
talk over for no gain.

Two limits, not one:

    max_total       4   how many downloads actually transfer at once
    per_provider    2   how many of those may belong to one platform

The per-platform cap is what keeps Instagram and TikTok from answering with 429s, and
it is enforced by giving each platform its own small executor rather than by taking a
second lock inside a shared worker. That distinction matters: with one shared pool of
four workers and a per-platform semaphore, four queued Reels would occupy every worker
and block on the semaphore, and a YouTube link queued behind them would never start.
Per-platform queues cannot head-of-line block each other.

Anything beyond the limits waits in its platform's queue and starts when a slot frees,
which is what the "Queued" rows on the download page are showing.
"""

import itertools
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from downloader import registry
from downloader.base import DownloadCancelled, DownloadError

# Four at once saturates an ordinary connection without any one platform seeing more
# than two. Both are overridable for anyone on a very fast or very slow line.
DEFAULT_MAX_TOTAL = 4
DEFAULT_PER_PROVIDER = 2

# Seconds between progress reports reaching the window. Ten a second is smooth to the
# eye and a small fraction of what yt-dlp emits on a large file.
UI_UPDATE_INTERVAL = 0.1

_ids = itertools.count(1)


def _limit(name, default):
    try:
        value = int(os.environ.get(name, ""))
    except ValueError:
        return default
    return value if value >= 1 else default


class DownloadJob:
    """One requested download, and everything a row needs to draw itself."""

    def __init__(self, provider, url, options):
        self.id = next(_ids)
        self.provider = provider
        self.provider_name = provider.name
        self.provider_label = provider.label
        self.url = url
        self.options = options

        # queued -> downloading -> done | error | cancelled
        self.state = "queued"
        self.title = url
        self.status_text = "Queued"
        # None means "running, but the total size is unknown", which fragmented
        # streams report constantly; the row shows an indeterminate bar for it.
        self.fraction = 0.0
        self.error = ""
        self.result = None

        self._cancelled = threading.Event()

    def cancel(self):
        self._cancelled.set()

    @property
    def cancel_requested(self):
        return self._cancelled.is_set()

    @property
    def finished(self):
        return self.state in ("done", "error", "cancelled")


class DownloadPool:
    """Owns the worker threads. One of these per app."""

    def __init__(self, post, on_update=None, on_finished=None):
        # post(fn) hands fn to the UI thread. Tk is not thread safe, so nothing here
        # touches a widget directly -- exactly how the transcription worker reports.
        self.post = post
        self.on_update = on_update
        self.on_finished = on_finished

        self.max_total = _limit("TRANSCRIBER_MAX_DOWNLOADS", DEFAULT_MAX_TOTAL)
        self.per_provider = _limit("TRANSCRIBER_MAX_PER_PLATFORM", DEFAULT_PER_PROVIDER)

        # The global cap. Acquired inside a worker that already holds one of its
        # platform's slots, and always released, so it cannot deadlock: every holder
        # is doing network work that ends.
        self._slots = threading.Semaphore(self.max_total)

        self._executors = {}
        self._jobs = []
        self._lock = threading.Lock()
        self._shutdown = False

    # ------------------------------------------------------------------ submission

    def find_active(self, provider_name, url):
        """An unfinished job for this exact link, if one is already running."""
        wanted = (url or "").strip()
        with self._lock:
            for job in self._jobs:
                if not job.finished and job.provider_name == provider_name \
                        and job.url.strip() == wanted:
                    return job
        return None

    def submit(self, provider_name, url, options=None):
        """Queue a download and return its job immediately.

        Submitting a link that is already downloading returns the job already doing it
        rather than starting a second. Two jobs on one post would race over the same
        part-file -- both write to the post's id in the platform's folder -- and the
        loser would corrupt the winner.
        """
        existing = self.find_active(provider_name, url)
        if existing is not None:
            return existing

        provider = registry.get_provider(provider_name)
        job = DownloadJob(provider, url, options)

        with self._lock:
            if self._shutdown:
                job.state = "cancelled"
                return job
            self._jobs.append(job)
            executor = self._executor_for(provider_name)

        executor.submit(self._run, job)
        return job

    def _executor_for(self, provider_name):
        """One small executor per platform, created on first use.

        Threads are named so a stack dump in the crash log says which platform a hung
        download belongs to.
        """
        executor = self._executors.get(provider_name)
        if executor is None:
            executor = ThreadPoolExecutor(
                max_workers=self.per_provider,
                thread_name_prefix="download-" + provider_name,
            )
            self._executors[provider_name] = executor
        return executor

    # --------------------------------------------------------------------- running

    def _run(self, job):
        # Cancelled while it sat in the queue, which is the common case when someone
        # changes their mind or closes the app.
        if job.cancel_requested or self._shutdown:
            return self._settle(job, "cancelled", "Cancelled")

        with self._slots:
            if job.cancel_requested or self._shutdown:
                return self._settle(job, "cancelled", "Cancelled")

            job.state = "downloading"
            job.status_text = "Starting..."
            self._notify(job)

            # yt-dlp calls its progress hook per chunk and per fragment, which on a
            # long download is thousands of calls. Every one of those would otherwise
            # become an after(0) on the Tk thread, and the UI spends its time redrawing
            # a label instead of responding. The job object always holds the latest
            # values; only how often the window is told is limited.
            last_sent = [0.0]

            def progress(fraction, status_text):
                job.fraction = fraction
                job.status_text = status_text

                now = time.monotonic()
                if now - last_sent[0] < UI_UPDATE_INTERVAL and fraction not in (None, 1.0):
                    return
                last_sent[0] = now
                self._notify(job)

            try:
                result = job.provider.download_audio(
                    job.url,
                    options=job.options,
                    progress_callback=progress,
                    check_cancel=lambda: job.cancel_requested or self._shutdown,
                )
            except DownloadCancelled:
                return self._settle(job, "cancelled", "Cancelled")
            except DownloadError as exc:
                return self._settle(job, "error", str(exc))
            except Exception as exc:
                # An adapter bug, a broken yt-dlp release, a full disk. The row has to
                # say something rather than sit at "Starting..." forever.
                return self._settle(job, "error", _unexpected(exc))

            job.result = result
            job.title = result.title
            job.fraction = 1.0
            return self._settle(job, "done", "Downloaded")

    def _settle(self, job, state, message):
        job.state = state
        job.status_text = message
        if state == "error":
            job.error = message
        if state != "done":
            job.fraction = 0.0
        self._notify(job)
        if self.on_finished:
            self.post(lambda: self.on_finished(job))

    def _notify(self, job):
        if self.on_update:
            self.post(lambda: self.on_update(job))

    # -------------------------------------------------------------------- lifecycle

    def active_count(self):
        with self._lock:
            return sum(1 for job in self._jobs if not job.finished)

    def cancel_all(self):
        with self._lock:
            jobs = list(self._jobs)
        for job in jobs:
            if not job.finished:
                job.cancel()

    def forget(self, job):
        """Drop a finished job from the list, once its row is gone."""
        with self._lock:
            if job in self._jobs:
                self._jobs.remove(job)

    def shutdown(self):
        """Stop everything, without waiting for it.

        Called from the closing sequence, which is already on a deadline: a download
        blocked on a socket can take its full timeout to notice, and the app must not
        sit there holding a window open while it does.
        """
        with self._lock:
            self._shutdown = True
            executors = list(self._executors.values())
        self.cancel_all()
        for executor in executors:
            executor.shutdown(wait=False, cancel_futures=True)


def _unexpected(exc):
    detail = str(exc).strip() or exc.__class__.__name__
    return "The download failed unexpectedly: " + detail
