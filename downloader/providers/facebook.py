from downloader.base import MediaDownloader
from downloader import ytdlp


class FacebookDownloader(MediaDownloader):
    """Facebook videos, Reels, Watch posts and fb.watch share links.

    Like Instagram, Facebook serves a muxed MP4, so the audio is copied out afterwards.
    Facebook link formats are unusually varied -- the same video reachable as
    /watch/?v=, /reel/, /videos/, /share/v/ or a fb.watch short link -- which is why
    the patterns below are broader than the others.
    """

    name = "facebook"
    label = "Facebook"
    folder_name = "Facebook"

    url_patterns = (
        r"^(https?://)?(www\.|m\.|web\.)?facebook\.com/.+/(videos|reel)/",
        r"^(https?://)?(www\.|m\.|web\.)?facebook\.com/(watch|reel|video|story\.php|share)/?",
        r"^(https?://)?(www\.|m\.|web\.)?facebook\.com/watch/?\?v=",
        r"^(https?://)?fb\.watch/[\w-]+",
        r"^(https?://)?(www\.)?fb\.com/.+",
    )

    def download_audio(self, url, options=None, progress_callback=None, check_cancel=None):
        return ytdlp.fetch(
            self,
            url,
            extra_options={
                "format": ytdlp.audio_format(options),
                "http_headers": {
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/131.0.0.0 Safari/537.36"
                    ),
                },
            },
            options=options,
            progress_callback=progress_callback,
            check_cancel=check_cancel,
        )
