"""The contract every platform adapter implements.

Deliberately shaped like transcriber/base.py: one abstract method, everything else
supplied by the base class, so adding a platform is a small, obvious piece of work.
A provider declares what it is and which links are its own, and implements
download_audio(). Nothing else is required of it.

Nothing in this package knows what a provider looks like on screen. Colours, icons,
placeholder text and help copy live in ctk_ui/provider_style.py, because they are
decisions about a window, not about a website -- and because this package has to keep
working in the installer, which has no UI at all. The only human-readable thing here is
`label`, which is data rather than styling: it is the platform's name, and it appears
in the error messages the adapters themselves raise.

The app never imports a provider directly. It asks downloader/registry.py, exactly as
it asks transcriber/registry.py for an engine.
"""

import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from transcriber.paths import get_download_dir


class DownloadCancelled(Exception):
    """Raised out of a download the user stopped. Not an error worth reporting."""


class DownloadError(Exception):
    """A failure with a message written for the person who pasted the link."""


@dataclass
class DownloadOptions:
    """Per-request settings the caller collects."""

    # Name of a browser whose cookies yt-dlp should borrow ("firefox", "chrome",
    # "edge", "brave"), or None to stay logged out. Instagram and Facebook serve
    # almost nothing to a logged-out client, so this is how private or
    # followers-only posts become reachable.
    cookies_from_browser: Optional[str] = None

    # Keep the highest-bitrate audio the platform offers instead of the smallest one
    # that is still good for speech. Off by default; see AUDIO_FORMAT in ytdlp.py.
    best_quality: bool = False


@dataclass
class DownloadResult:
    """What the caller needs in order to show a row for the finished file."""

    path: str
    title: str
    duration: float
    provider: str
    provider_label: str
    url: str = ""


class MediaDownloader(ABC):
    """One platform. Subclasses implement download_audio() and nothing else."""

    # Identity. `name` is the key in the registry; `label` is the platform's name as
    # people write it, used in error messages and by the UI.
    name = ""
    label = ""

    # Folder under downloads/ holding everything from this platform, so a person
    # looking for a reel they saved knows where to look without searching.
    folder_name = ""

    # Patterns deciding whether a pasted link belongs to this platform. Matched
    # against the whole URL, case-insensitively.
    url_patterns = ()

    # ------------------------------------------------------------------ identity

    @classmethod
    def matches(cls, url):
        """Whether this adapter recognises the link."""
        text = (url or "").strip()
        return any(re.search(pattern, text, re.IGNORECASE) for pattern in cls.url_patterns)

    # ------------------------------------------------------------------- storage

    def output_dir(self):
        """This platform's folder, created on demand."""
        folder = os.path.join(get_download_dir(), self.folder_name or self.name)
        os.makedirs(folder, exist_ok=True)
        return folder

    # ---------------------------------------------------------------- the method

    @abstractmethod
    def download_audio(self, url, options=None, progress_callback=None, check_cancel=None):
        """Fetch the audio of one post and return a DownloadResult.

        The file lands in output_dir(), named after the video's title or caption, and
        holds audio only -- adapters whose platform serves a muxed MP4 strip the video
        track by copying the audio stream out, never by re-encoding it.

        progress_callback(fraction, status_text) is called with a 0..1 float and a
        line to show beside the row; platforms that cannot report a total call it with
        a None fraction and a size instead.
        check_cancel() is polled throughout; a truthy result raises DownloadCancelled.
        """
