from downloader.base import MediaDownloader
from downloader import ytdlp


class TikTokDownloader(MediaDownloader):
    """TikTok videos, including vm./vt. short links.

    TikTok only ever serves a muxed MP4, so every download here goes through the remux
    step. Short links redirect to the canonical post, which yt-dlp follows on its own.

    TikTok is the quickest of the four to start refusing a connection that asks for too
    much at once, which is the reason for the per-platform limit of two in the pool.
    """

    name = "tiktok"
    label = "TikTok"
    folder_name = "TikTok"

    url_patterns = (
        r"^(https?://)?(www\.|m\.)?tiktok\.com/@[\w.-]+/(video|photo)/\d+",
        r"^(https?://)?(www\.)?tiktok\.com/t/[\w-]+",
        r"^(https?://)?(vm|vt)\.tiktok\.com/[\w-]+",
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
