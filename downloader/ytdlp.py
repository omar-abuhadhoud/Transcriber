"""The shared machinery every adapter's download_audio() runs on.

Adapters differ only in the options they pass here: which format to ask for, which
headers a platform insists on, whether the result needs its video track stripped. The
fetching, naming, progress reporting, cancellation and error translation are the same
everywhere and live in one place.

Nothing is ever re-encoded. Where a platform offers an audio-only stream it is taken as
it is; where it only serves a muxed MP4 the audio packets are copied out by
downloader/remux.py. Re-encoding to MP3 would cost minutes of CPU per file and buy
nothing, because transcription decodes with PyAV, which reads all of these already.
"""

import os
import shutil

from downloader import remux
from downloader.base import DownloadCancelled, DownloadError, DownloadResult
from downloader.naming import safe_stem, unique_path

# Pieces of a fragmented stream fetched at once. Instagram, TikTok and Facebook serve
# HLS/DASH, where each fragment is a separate request, and one at a time leaves most of
# the connection idle. Eight is where the gain flattens out, and well short of what a
# platform reads as abuse.
FRAGMENTS_AT_ONCE = 8

# Highest audio bitrate worth fetching, in kbps.
#
# This is the single biggest lever on download time. YouTube offers the same speech at
# 49 kbps and at 130 kbps; over five hours that is 105 MB against 279 MB, for a file
# that is about to be resampled to 16 kHz mono and handed to an ASR model that cannot
# tell the difference. Asking for "the best audio" would spend two and a half times the
# bandwidth to discard the extra on the next line.
#
# 80 leaves room to take a 64 kbps stream where a 48 kbps one is not offered, and the
# selector always falls back to whatever exists if nothing is under the cap.
SPEECH_BITRATE_CAP = 80

# Bytes per HTTP range request. A long YouTube download on one open socket gets
# throttled hard; asking for it in chunks keeps the rate up. Irrelevant to fragmented
# streams, which are already many small requests.
HTTP_CHUNK_SIZE = 10 * 1024 * 1024


def audio_format(options, prefer_ext=None):
    """The format selector to ask yt-dlp for.

    Built rather than hard-coded because the choice depends on what the file is for.
    Everything here is destined for transcription, so the smallest adequate stream
    wins; DownloadOptions.best_quality asks for the largest instead, for anyone who
    wants to keep the audio to listen to.
    """
    best = options is not None and getattr(options, "best_quality", False)

    if best:
        return ("bestaudio[ext=%s]/bestaudio/best" % prefer_ext) if prefer_ext else "bestaudio/best"

    cap = SPEECH_BITRATE_CAP
    choices = []
    if prefer_ext:
        choices.append("bestaudio[ext=%s][abr<=%d]" % (prefer_ext, cap))
    choices.append("bestaudio[abr<=%d]" % cap)
    if prefer_ext:
        choices.append("bestaudio[ext=%s]" % prefer_ext)
    # Nothing under the cap, or no bitrate advertised at all, which is the norm on
    # Instagram and TikTok. Take what there is.
    choices.extend(["bestaudio", "best"])
    return "/".join(choices)


def _accelerator():
    """Hand the transfer to aria2c, when the user has asked for it and it is installed.

    aria2c opens many connections to one file, which is the only real way to speed up a
    single large download; yt-dlp on its own is one socket plus range requests. It is
    opt-in rather than automatic because yt-dlp reports far coarser progress through an
    external downloader, so the bar stops being a bar -- a bad trade for a reel, a good
    one for a five-hour recording.
    """
    if os.environ.get("TRANSCRIBER_USE_ARIA2", "") not in ("1", "true", "yes"):
        return {}
    if not shutil.which("aria2c"):
        return {}

    return {
        "external_downloader": {"default": "aria2c"},
        "external_downloader_args": {
            "aria2c": [
                "-x", "16",           # connections per server
                "-s", "16",           # split the file 16 ways
                "-k", "1M",           # minimum piece size
                "--file-allocation=none",
                "--summary-interval=0",
            ],
        },
    }


class _Cancelled(Exception):
    """Thrown out of the progress hook. Private, because yt-dlp may rewrap it."""


class _Silent:
    """yt-dlp logs to stderr by default; this app has its own error surface."""

    def debug(self, message):
        pass

    warning = error = debug


def base_options(downloader, options, progress_hook):
    """Options common to every platform."""
    settings = {
        "paths": {"home": downloader.output_dir()},
        # Downloaded under the post's id and renamed to its caption afterwards: ids are
        # always legal filenames, captions are not, and a half-finished download should
        # not be sitting there already wearing the final name.
        "outtmpl": "%(id)s.%(ext)s",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "logger": _Silent(),
        "progress_hooks": [progress_hook],
        "concurrent_fragment_downloads": FRAGMENTS_AT_ONCE,
        "http_chunk_size": HTTP_CHUNK_SIZE,
        # Resume rather than restart. On a five-hour recording a dropped connection an
        # hour in is otherwise an hour thrown away, and the .part file is already
        # sitting there under the post's id.
        "continuedl": True,
        "retries": 10,
        "fragment_retries": 10,
        # Long transfers are exactly when a transient 5xx or a reset shows up.
        "file_access_retries": 5,
        # No postprocessing at all, which is what keeps ffmpeg out of the install.
        "postprocessors": [],
        "writethumbnail": False,
        "writeinfojson": False,
        "writesubtitles": False,
        "overwrites": True,
        # A stray channel or playlist link must not quietly start a hundred downloads.
        "playlist_items": "1",
    }

    if options is not None and options.cookies_from_browser:
        settings["cookiesfrombrowser"] = (options.cookies_from_browser,)

    settings.update(_accelerator())
    return settings


def fetch(downloader, url, extra_options=None, options=None,
          progress_callback=None, check_cancel=None, strip_video=True):
    """Download one post's audio. The body of every adapter's download_audio()."""
    from yt_dlp import YoutubeDL

    url = (url or "").strip()
    if not url:
        raise DownloadError("No link was given.")

    def hook(status):
        if check_cancel and check_cancel():
            raise _Cancelled()
        if progress_callback:
            _report(progress_callback, status)

    settings = base_options(downloader, options, hook)
    settings.update(extra_options or {})

    if progress_callback:
        progress_callback(None, "Reading the link...")

    try:
        with YoutubeDL(settings) as ydl:
            info = ydl.extract_info(url, download=True)
    except _Cancelled:
        raise DownloadCancelled()
    except Exception as exc:
        # yt-dlp wraps exceptions raised inside a hook, so a cancellation can arrive
        # dressed as a download failure. The user's own request is not an error.
        if check_cancel and check_cancel():
            raise DownloadCancelled()
        raise DownloadError(explain(exc, downloader)) from exc

    if check_cancel and check_cancel():
        raise DownloadCancelled()

    info = _first_entry(info)
    source_path = _downloaded_path(info)
    if not source_path or not os.path.exists(source_path):
        raise DownloadError(
            downloader.label + " accepted the link but produced no audio file. "
            "The post may have been removed."
        )

    if strip_video:
        if progress_callback:
            progress_callback(None, "Extracting audio...")
        source_path = remux.audio_only_path(source_path)

    final_path = _rename_to_title(source_path, downloader, info)

    if progress_callback:
        progress_callback(1.0, "Downloaded")

    return DownloadResult(
        path=final_path,
        title=os.path.splitext(os.path.basename(final_path))[0],
        duration=float(info.get("duration") or 0),
        provider=downloader.name,
        provider_label=downloader.label,
        url=url,
    )


# ----------------------------------------------------------------------- progress


def _report(progress_callback, status):
    state = status.get("status")

    if state == "finished":
        progress_callback(None, "Finishing...")
        return
    if state != "downloading":
        return

    done = status.get("downloaded_bytes") or 0
    total = status.get("total_bytes") or status.get("total_bytes_estimate") or 0
    speed = status.get("speed")

    detail = _megabytes(done) + " of " + _megabytes(total) if total else _megabytes(done)
    if speed:
        detail += "  -  " + _megabytes(speed) + "/s"

    # A fragmented manifest often reports no total. A None fraction tells the row to
    # show an indeterminate bar rather than one stuck at zero.
    fraction = min(done / total, 1.0) if total else None
    progress_callback(fraction, detail)


def _megabytes(value):
    return "{0:.1f} MB".format((value or 0) / (1024 * 1024))


# -------------------------------------------------------------------------- files


def _first_entry(info):
    """Unwrap the single entry from a link that turned out to be a playlist."""
    if isinstance(info, dict) and info.get("entries"):
        entries = [entry for entry in info["entries"] if entry]
        if entries:
            return entries[0]
    return info or {}


def _downloaded_path(info):
    downloads = info.get("requested_downloads") or []
    if downloads:
        path = downloads[0].get("filepath")
        if path:
            return path
    return info.get("filepath") or info.get("_filename")


def _rename_to_title(source_path, downloader, info):
    """Give the file the post's caption as its name.

    Renaming afterwards, rather than templating the caption into yt-dlp's outtmpl,
    keeps every odd caption -- newlines, emoji, a slash, nothing at all -- out of the
    download itself.
    """
    fallback = downloader.label + " " + str(info.get("id") or "audio")
    stem = safe_stem(_title_of(info), fallback=fallback)
    extension = os.path.splitext(source_path)[1] or ".m4a"

    target = unique_path(os.path.dirname(source_path), stem, extension)
    try:
        os.replace(source_path, target)
    except OSError:
        # Locked by an antivirus scan, most often. The download itself succeeded, and a
        # file named after its id beats a failed download.
        return source_path
    return target


def _title_of(info):
    """The caption, however this extractor happens to expose it.

    Reels and TikToks often have no title field worth the name, and the first line of
    the description is the caption a person would actually recognise.
    """
    title = (info.get("title") or "").strip()

    # Some extractors synthesise a title out of the id when there is no real one.
    if title and title.lower() not in {str(info.get("id") or "").lower(), "video"}:
        return title

    description = (info.get("description") or "").strip()
    if description:
        return description.splitlines()[0].strip()

    return title or info.get("fulltitle") or ""


# ------------------------------------------------------------------------- errors


def explain(exc, downloader):
    """Turn a yt-dlp failure into a sentence worth showing someone."""
    text = str(exc)
    lowered = text.lower()
    label = downloader.label

    if "cookie" in lowered and ("browser" in lowered or "decrypt" in lowered):
        return (
            "The browser's cookies could not be read. Chrome and Edge encrypt theirs "
            "while running, so close the browser and try again, or use Firefox."
        )
    if any(needle in lowered for needle in
           ("sign in", "log in", "login required", "private", "not available on this app")):
        return (
            "This " + label + " post needs a login. Tick 'Use my browser login' in the "
            "download box and pick the browser you are signed in with."
        )
    if "429" in lowered or "too many requests" in lowered or "rate-limit" in lowered:
        return (
            label + " is rate-limiting this connection. Wait a few minutes and try "
            "again, or download fewer at once."
        )
    if "unsupported url" in lowered:
        return "That link is not one " + label + " content can be read from."
    if any(needle in lowered for needle in
           ("video unavailable", "has been removed", "404", "410")):
        return "That post no longer exists, or is not visible from this country."
    if "geo" in lowered and "restrict" in lowered:
        return "That post is blocked in this country."
    if "no video formats" in lowered or "no formats" in lowered:
        return (
            label + " returned nothing playable for that link. If it is a photo post "
            "rather than a video, there is no audio on it to download."
        )
    # Parenthesised, because `a or b and c` reads as `a or (b and c)` and the intent
    # here is genuinely that, not the left-to-right reading it looks like.
    if "timed out" in lowered or ("connection" in lowered and "unable" in lowered):
        return "The connection dropped during the download. Try again."

    # Nothing recognised: yt-dlp's own wording, tidied.
    cleaned = text.replace("ERROR: ", "").strip()
    return cleaned or ("The " + label + " download failed.")
