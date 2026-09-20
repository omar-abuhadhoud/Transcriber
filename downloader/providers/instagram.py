from downloader.base import MediaDownloader
from downloader import ytdlp


class InstagramDownloader(MediaDownloader):
    """Reels, feed videos and IGTV posts.

    Instagram serves a muxed MP4 rather than an audio-only stream, so the file arrives
    with its video track and the remux step copies the audio out of it.

    It is also the strictest of the four about logged-out clients: anything from a
    private account, and increasingly a good deal that is public, returns nothing
    without a session. That is what the browser-login checkbox is for.
    """

    name = "instagram"
    label = "Instagram"
    folder_name = "Instagram"

    url_patterns = (
        r"^(https?://)?(www\.)?instagram\.com/(reels?|p|tv|share)/",
        r"^(https?://)?(www\.)?instagram\.com/[\w.]+/(reels?|p|tv)/",
        r"^(https?://)?instagr\.am/(reels?|p|tv)/",
    )

    def download_audio(self, url, options=None, progress_callback=None, check_cancel=None):
        return ytdlp.fetch(
            self,
            url,
            extra_options={
                "format": ytdlp.audio_format(options),
                # Instagram varies what it returns by client; a plain desktop browser
                # signature is the one it treats most normally.
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
