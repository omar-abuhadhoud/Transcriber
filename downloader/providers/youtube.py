from downloader.base import MediaDownloader
from downloader import ytdlp


class YouTubeDownloader(MediaDownloader):
    """YouTube videos, Shorts and live replays.

    The one platform of the four that publishes a genuine audio-only stream, so a
    download here transfers only the audio and never touches the video track at all.
    An m4a is preferred over the (often smaller) Opus/WebM stream because Windows can
    play it without anything installed, which matters for a file the user keeps.
    """

    name = "youtube"
    label = "YouTube"
    folder_name = "YouTube"

    url_patterns = (
        r"^(https?://)?(www\.|m\.|music\.)?youtube\.com/(watch\?|shorts/|live/|embed/|v/)",
        r"^(https?://)?(www\.)?youtu\.be/[\w-]+",
    )

    def download_audio(self, url, options=None, progress_callback=None, check_cancel=None):
        return ytdlp.fetch(
            self,
            url,
            extra_options={
                # m4a first for playability, then any audio-only stream, and only then
                # a muxed file -- which the remux step would strip. The selector caps
                # the bitrate, because YouTube offers the same speech at 49 kbps and
                # at 130 kbps and only one of those is worth waiting for.
                "format": ytdlp.audio_format(options, prefer_ext="m4a"),
            },
            options=options,
            progress_callback=progress_callback,
            check_cancel=check_cancel,
        )
