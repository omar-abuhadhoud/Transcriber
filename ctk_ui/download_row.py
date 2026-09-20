"""One line in the download list: what is being fetched, and how far along it is.

The queue's rows are MediaItem; these are the equivalent for the download page, and
they are deliberately lighter. A download has no output to save, copy or view -- when
it finishes it becomes a MediaItem over on the queue page -- so a row here only has to
show progress and offer a way to stop.
"""

import customtkinter as ctk

from ctk_ui import theme
from ctk_ui.provider_style import style_for
from ctk_ui.theme import ui_font

STATE_COLORS = {
    "queued": theme.MUTED,
    "downloading": "#3498db",
    "done": theme.SUCCESS,
    "error": theme.DANGER,
    "cancelled": theme.MUTED,
}


class DownloadRow(ctk.CTkFrame):
    """A row bound to one DownloadJob."""

    def __init__(self, parent, job, on_cancel=None, on_remove=None, **kwargs):
        super().__init__(parent, **kwargs)

        self.job = job
        self.on_cancel = on_cancel
        self.on_remove = on_remove
        # Tracked so the indeterminate animation is only started and stopped once;
        # restarting it on every progress event makes the bar stutter.
        self._indeterminate = False

        top = ctk.CTkFrame(self, fg_color="transparent", width=1, height=1)
        top.pack(fill="x", padx=10, pady=(8, 2))

        # Packed right-to-left, and the button first, so that however long a status
        # message turns out to be, the control that stops the download is still on
        # screen. A failure message is exactly when it is most needed.
        self.btn_action = ctk.CTkButton(
            top,
            text="✕",
            width=28,
            height=28,
            font=ui_font(12),
            fg_color="#7f8c8d",
            hover_color="#95a5a6",
            command=self._action,
        )
        self.btn_action.pack(side="right", padx=(10, 0))

        self.lbl_status = ctk.CTkLabel(
            top,
            text=job.status_text,
            anchor="e",
            justify="right",
            font=ui_font(11),
            text_color=STATE_COLORS["queued"],
            wraplength=320,
        )
        self.lbl_status.pack(side="right", padx=(10, 0))

        left = ctk.CTkFrame(top, fg_color="transparent", width=1, height=1)
        left.pack(side="left", fill="both", expand=True)

        self.lbl_title = ctk.CTkLabel(
            left,
            text=_shorten(job.url),
            anchor="w",
            justify="left",
            font=ui_font(12, "bold"),
        )
        self.lbl_title.pack(anchor="w", fill="x")

        self.lbl_provider = ctk.CTkLabel(
            left,
            text=job.provider_label,
            anchor="w",
            font=ui_font(10),
            # The job carries a platform name; what colour that is belongs here,
            # not on the adapter that fetched it.
            text_color=style_for(job.provider_name).accent,
        )
        self.lbl_provider.pack(anchor="w")

        self.progress = ctk.CTkProgressBar(self, height=6)
        self.progress.set(0)
        self.progress.pack(fill="x", padx=10, pady=(2, 8))

        self.refresh()

    # ------------------------------------------------------------------- updating

    def refresh(self):
        """Redraw from the job. Called on the UI thread whenever the pool reports."""
        if not self.winfo_exists():
            return

        job = self.job

        if job.title and job.title != job.url:
            self.lbl_title.configure(text=_shorten(job.title))

        self.lbl_status.configure(
            text=_shorten(job.status_text, 70),
            text_color=STATE_COLORS.get(job.state, theme.MUTED),
        )

        if job.state == "downloading" and job.fraction is None:
            self._set_indeterminate(True)
        else:
            self._set_indeterminate(False)
            self.progress.set(job.fraction if job.fraction is not None else 0)

        if job.finished:
            # Nothing left to stop, so the cross becomes "clear this away".
            self.btn_action.configure(text="✕", fg_color="#7f8c8d", hover_color="#95a5a6")

    def _set_indeterminate(self, on):
        """A fragmented stream reports no total, so the bar sweeps instead of filling."""
        if on == self._indeterminate:
            return
        self._indeterminate = on

        try:
            if on:
                self.progress.configure(mode="indeterminate")
                self.progress.start()
            else:
                self.progress.stop()
                self.progress.configure(mode="determinate")
        except Exception:
            # The widget went away mid-update while the window was closing.
            pass

    def _action(self):
        if self.job.finished:
            if self.on_remove:
                self.on_remove(self)
        elif self.on_cancel:
            self.on_cancel(self)

    def destroy(self):
        # An indeterminate bar schedules its own after() loop; leaving it running
        # against a destroyed widget raises out of Tk's callback handler.
        self._set_indeterminate(False)
        super().destroy()


def _shorten(text, limit=90):
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"
