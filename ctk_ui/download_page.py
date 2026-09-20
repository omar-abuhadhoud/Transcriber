"""The second tab: pick a platform, paste a link, watch it arrive.

The page owns the download pool and the rows describing it. It knows nothing about
transcription -- when a download finishes it hands the result to the callback the app
gave it, and the app is what puts a row on the queue page and raises the notification.
"""

import os
import subprocess

import customtkinter as ctk

from ctk_ui import theme
from ctk_ui.download_row import DownloadRow
from ctk_ui.provider_style import all_views
from ctk_ui.provider_tile import tile_grid
from ctk_ui.theme import ui_font
from ctk_ui.url_dialog import UrlDialog
from downloader.pool import DownloadPool
from transcriber.paths import get_download_dir


class DownloadPage(ctk.CTkFrame):
    """Tiles on top, the list of what is downloading underneath."""

    def __init__(self, parent, on_downloaded, on_failed=None, on_counts_changed=None, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)

        self.on_downloaded = on_downloaded
        self.on_failed = on_failed
        self.on_counts_changed = on_counts_changed
        self.rows = {}

        self.pool = DownloadPool(
            # Everything the pool reports arrives on a worker thread; after(0) is how
            # it reaches Tk, exactly as the transcription worker does it.
            post=self._post_to_ui,
            on_update=self._job_updated,
            on_finished=self._job_finished,
        )

        # Row 3 is the download list, and it is the one that absorbs spare height; the
        # tiles above it keep their natural size.
        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build_header()
        self._build_tiles()
        self._build_list()

    # ------------------------------------------------------------------- building

    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(14, 0))

        ctk.CTkLabel(
            header,
            text="Download audio from a link",
            font=ui_font(17, "bold"),
        ).pack(side="left")

        ctk.CTkButton(
            header,
            text="Open downloads folder",
            width=170,
            height=32,
            font=ui_font(12),
            fg_color="transparent",
            border_width=1,
            text_color=("gray20", "gray85"),
            command=self.open_folder,
        ).pack(side="right")

        ctk.CTkLabel(
            self,
            text=(
                "Only the audio is downloaded, and it is never re-encoded. Files are "
                "saved per platform under " + get_download_dir() + ", named after the "
                "caption, and added to the transcription queue when they land."
            ),
            font=ui_font(11),
            text_color=theme.MUTED,
            anchor="w",
            justify="left",
            wraplength=900,
        ).grid(row=1, column=0, sticky="ew", padx=20, pady=(4, 0))

    def _build_tiles(self):
        # Built straight from the registry, so registering a fifth platform puts a
        # fifth tile here without touching this file. all_views() is what pairs each
        # adapter with its colours, which the adapter itself knows nothing about.
        self.tiles = tile_grid(self, all_views(), self.open_dialog)
        self.tiles.grid(row=2, column=0, sticky="n", pady=(18, 0))

    def _build_list(self):
        self.list_area = ctk.CTkScrollableFrame(self, label_text="Downloads")
        self.list_area.grid(row=3, column=0, sticky="nsew", padx=20, pady=(10, 14))
        self.list_area.grid_columnconfigure(0, weight=1)

        self.lbl_empty = ctk.CTkLabel(
            self.list_area,
            text="Nothing downloading. Pick a platform above to start.",
            font=ui_font(12),
            text_color=theme.MUTED,
        )
        self.lbl_empty.pack(pady=18)

        ctk.CTkLabel(
            self,
            text=(
                "Up to {0} downloads at a time, and at most {1} from the same platform, "
                "so a burst never trips a rate limit. Anything else waits its turn."
            ).format(self.pool.max_total, self.pool.per_provider),
            font=ui_font(10),
            text_color=theme.MUTED,
        ).grid(row=4, column=0, pady=(0, 10))

    # ------------------------------------------------------------------- starting

    def open_dialog(self, info):
        UrlDialog(self.winfo_toplevel(), info, on_submit=lambda url, options:
                  self.start_download(info.name, url, options))

    def start_download(self, provider_name, url, options):
        job = self.pool.submit(provider_name, url, options)

        # The pool hands back the job already running when the same link is submitted
        # twice, so point at the row that exists rather than drawing a second one for
        # the same download.
        if job.id in self.rows:
            self._highlight(self.rows[job.id])
            return job

        row = DownloadRow(
            self.list_area,
            job,
            on_cancel=self._cancel_row,
            on_remove=self._remove_row,
        )
        row.pack(fill="x", pady=3, padx=5)
        self.rows[job.id] = row

        self.lbl_empty.pack_forget()
        self._counts_changed()
        return job

    def _highlight(self, row):
        """Draw attention to a row that already exists.

        The link was submitted twice, so nothing new happens; without this the second
        press would look like it did nothing at all.
        """
        try:
            original = row.cget("fg_color")
            row.configure(fg_color=theme.ACCENT)
            row.after(600, lambda: row.winfo_exists() and row.configure(fg_color=original))
        except Exception:
            pass

    # -------------------------------------------------------------------- updates

    def _post_to_ui(self, fn):
        """Hand a pool callback to the Tk thread.

        Guarded, because the pool reports from worker threads that outlive this
        widget: closing the app tears the window down while downloads are still
        noticing they have been cancelled, and after() on a destroyed widget raises
        TclError out of a thread with nothing to catch it.
        """
        try:
            self.after(0, fn)
        except Exception:
            pass

    def _job_updated(self, job):
        row = self.rows.get(job.id)
        if row is not None and row.winfo_exists():
            row.refresh()

    def _job_finished(self, job):
        self._job_updated(job)
        self._counts_changed()

        if job.state == "done" and job.result is not None:
            self.on_downloaded(job.result)
        elif job.state == "error" and self.on_failed:
            self.on_failed(job)

    def _counts_changed(self):
        if self.on_counts_changed:
            self.on_counts_changed(self.pool.active_count())

    # -------------------------------------------------------------------- removing

    def _cancel_row(self, row):
        row.job.cancel()
        row.job.status_text = "Cancelling..."
        row.refresh()

    def _remove_row(self, row):
        self.pool.forget(row.job)
        self.rows.pop(row.job.id, None)
        row.destroy()

        if not self.rows:
            self.lbl_empty.pack(pady=18)

    # --------------------------------------------------------------------- folder

    def open_folder(self):
        folder = get_download_dir()
        os.makedirs(folder, exist_ok=True)
        try:
            os.startfile(folder)
        except AttributeError:
            # Not Windows. The app is Windows-only in practice, but a dev machine
            # should not crash on a button.
            subprocess.Popen(["xdg-open", folder])

    # ------------------------------------------------------------------- shutdown

    def shutdown(self):
        self.pool.shutdown()
