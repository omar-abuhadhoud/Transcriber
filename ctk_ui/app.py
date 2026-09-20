"""The window: an update bar, a tab strip, and whichever page is showing.

The app used to be the transcription queue. It is now a shell over two pages, and it
deliberately owns very little: the window, the update banner, the notifications, and
the closing sequence. The queue page owns transcription, the download page owns
downloading, and the only thing that crosses between them is a finished download
arriving as a new row on the queue.

Both pages are built at startup and stay built. Switching tabs grids one and ungrids
the other, so a download keeps running while the queue is on screen and the queue's
worker keeps going while someone is pasting a link.
"""

import os
import sys
import threading
import time
import traceback
from datetime import datetime
from tkinter import messagebox

import customtkinter as ctk

import global_vars
from ctk_ui import theme
from ctk_ui.download_page import DownloadPage
from ctk_ui.queue_page import QueuePage
from ctk_ui.tabs import TabBar
from ctk_ui.theme import ui_font
from ctk_ui.toast import ToastHost
from transcriber.paths import get_log_dir, resource_path
from transcriber.util import Util
from transcriber.version import __version__

# --- CONFIGURATION ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

QUEUE_TAB = "queue"
DOWNLOAD_TAB = "download"


def app_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(".")


def log_runtime_error(message, exc=None):
    # Per-user, not beside the program: an update replaces the program folder
    # wholesale, and a crash log that disappears with it helps nobody.
    log_dir = get_log_dir()
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "runtime.log")
    with open(log_path, "a", encoding="utf-8") as log_file:
        log_file.write("\n" + "=" * 72 + "\n")
        log_file.write(f"{datetime.now().isoformat(timespec='seconds')} - {message}\n")
        if exc is not None:
            log_file.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))


class TranscriberQueueApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        os.makedirs(global_vars.rec_folder, exist_ok=True)

        # --- WINDOW SETUP ---
        self.title(f"Transcriber {__version__}")
        self.iconbitmap(resource_path("icon.ico"))
        self.after(0, lambda: self.state('zoomed'))
        self.minsize(820, 520)
        self.grid_rowconfigure(2, weight=1)  # The page area expands
        self.grid_columnconfigure(0, weight=1)

        # --- 0. UPDATE BANNER (row 0, hidden until a newer release is found) ---
        self.build_update_banner()

        # --- 1. TABS ---
        self.tab_bar = TabBar(
            self,
            tabs=[(QUEUE_TAB, "Transcription Queue"), (DOWNLOAD_TAB, "Download")],
            command=self.show_tab,
        )
        self.tab_bar.grid(row=1, column=0, sticky="w", padx=20, pady=(10, 0))

        # --- 2. PAGES ---
        self.build_pages()

        # --- 3. NOTIFICATIONS, over everything ---
        self.toasts = ToastHost(self)
        self.toasts.place_in_corner()

        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Optimize window state changes
        self.bind("<Map>", self._on_restore)

        self.start_update_check()

    # ------------------------------------------------------------------- the pages

    def build_pages(self):
        self.queue_page = QueuePage(self, log_error=log_runtime_error)
        self.download_page = DownloadPage(
            self,
            on_downloaded=self.on_download_finished,
            on_failed=self.on_download_failed,
            on_counts_changed=self.on_download_counts_changed,
        )

        self.pages = {QUEUE_TAB: self.queue_page, DOWNLOAD_TAB: self.download_page}
        for page in self.pages.values():
            page.grid(row=2, column=0, sticky="nsew")
            page.grid_remove()

        self.show_tab(self.tab_bar.active or QUEUE_TAB)

    def show_tab(self, key):
        # Called by the tab bar during its own construction, before the pages exist.
        for name, page in getattr(self, "pages", {}).items():
            if name == key:
                page.grid()
            else:
                page.grid_remove()

        # The toast stack is placed rather than gridded, so a page shown afterwards
        # would otherwise be drawn over it.
        if hasattr(self, "toasts"):
            self.toasts.lift()

    # -------------------------------------------------------------- download events

    def on_download_finished(self, result):
        """A download landed: put it in the queue and say so."""
        try:
            self.queue_page.add_downloaded(result)
        except Exception as exc:
            log_runtime_error("Could not queue the downloaded file " + str(result.path), exc)
            self.toasts.show(
                "Downloaded, but not queued",
                str(exc),
                kind="error",
            )
            return

        duration = Util.format_duration(result.duration)
        self.toasts.show(
            result.title,
            "Downloaded from " + result.provider_label
            + (" (" + duration + ")" if result.duration else "")
            + " and added to the transcription queue.",
            kind="success",
            # Clicking the notification takes you to the row it is talking about.
            on_click=lambda: self.tab_bar.select(QUEUE_TAB),
        )

    def on_download_failed(self, job):
        self.toasts.show(
            job.provider_label + " download failed",
            job.error,
            kind="error",
            timeout=12000,
        )

    def on_download_counts_changed(self, count):
        self.tab_bar.set_badge(DOWNLOAD_TAB, count)

    # ----------------------------------------------------------------- updates

    def build_update_banner(self):
        """A strip above the header, shown only when a newer release exists."""
        self.pending_update = None

        self.update_banner = ctk.CTkFrame(self, fg_color=theme.ACCENT)
        self.update_banner.grid(row=0, column=0, sticky="ew", padx=20, pady=(10, 0))
        self.update_banner.grid_remove()

        self.lbl_update = ctk.CTkLabel(
            self.update_banner,
            text="",
            font=ui_font(12, "bold"),
            text_color="white",
        )
        self.lbl_update.pack(side="left", padx=15, pady=8)

        self.btn_update_dismiss = ctk.CTkButton(
            self.update_banner,
            text="Later",
            width=70,
            height=28,
            fg_color="transparent",
            border_width=1,
            command=lambda: self.update_banner.grid_remove(),
        )
        self.btn_update_dismiss.pack(side="right", padx=(5, 15), pady=6)

        self.btn_update_install = ctk.CTkButton(
            self.update_banner,
            text="Update now",
            width=110,
            height=28,
            fg_color="white",
            text_color=theme.ACCENT,
            hover_color="#e0e0e0",
            command=self.on_update_clicked,
        )
        self.btn_update_install.pack(side="right", padx=5, pady=6)

    def start_update_check(self):
        """Ask GitHub for a newer release, off the UI thread.

        Daemon thread with no error surface: a failed check leaves the banner hidden,
        which is exactly what a user with no internet should see.
        """
        def worker():
            try:
                from transcriber import update as updater

                found = updater.check_for_update()
            except Exception:
                return
            if found:
                self.after(0, lambda: self.show_update_banner(found))

        threading.Thread(target=worker, daemon=True).start()

    def show_update_banner(self, found):
        self.pending_update = found
        size_mb = (found.get("size") or 0) / (1024 * 1024)
        detail = f"  ({size_mb:.0f} MB)" if size_mb >= 1 else ""
        self.lbl_update.configure(
            text=f"Transcriber {found['version']} is available{detail}. "
                 f"Your models and GPU runtime are kept."
        )
        self.update_banner.grid()

    def on_update_clicked(self):
        """Download the setup exe, then hand over to the wizard and quit."""
        if not self.pending_update:
            return

        if self.queue_page.queue_is_busy():
            messagebox.showinfo(
                "Update",
                "Finish or cancel the current transcriptions first, then update.",
            )
            return

        if self.download_page.pool.active_count():
            messagebox.showinfo(
                "Update",
                "Wait for the downloads to finish, or cancel them, then update.",
            )
            return

        self.btn_update_install.configure(state="disabled", text="Downloading...")
        self.btn_update_dismiss.configure(state="disabled")

        def worker():
            from transcriber import update as updater

            try:
                def on_progress(done, total):
                    if total:
                        percent = int(done * 100 / total)
                        self.after(0, lambda: self.btn_update_install.configure(
                            text=f"{percent}%"))

                installer = updater.download_installer(
                    self.pending_update, progress_callback=on_progress
                )
                self.after(0, lambda: self.finish_update(installer))
            except Exception as exc:
                log_runtime_error("Update download failed", exc)
                self.after(0, lambda: self.update_failed(exc))

        threading.Thread(target=worker, daemon=True).start()

    def update_failed(self, exc):
        self.btn_update_install.configure(state="normal", text="Update now")
        self.btn_update_dismiss.configure(state="normal")
        messagebox.showerror(
            "Update",
            f"The update could not be downloaded.\n\n{exc}\n\n"
            f"You can download it by hand from:\n{self.pending_update.get('page', '')}",
        )

    def finish_update(self, installer_path):
        """Start the wizard, then leave.

        The app must be gone before the wizard replaces its files, and it holds the
        mutex the wizard waits on, so this exits immediately rather than unwinding.
        """
        from transcriber import update as updater

        try:
            updater.launch_installer(installer_path)
        except Exception as exc:
            log_runtime_error("Could not start the updater", exc)
            self.update_failed(exc)
            return

        os._exit(0)

    def _on_restore(self, event):
        """Refresh once after the window is restored.

        <Map> also fires for every child widget, and each row adds a dozen of them, so
        without this guard adding files schedules hundreds of full-queue refreshes.
        """
        if event.widget is not self:
            return
        self.queue_page.refresh_after_restore()

    # ------------------------------------------------------------------- shutdown

    def on_closing(self):
        """Entry point when the user clicks X."""

        # 1. Disable the main window so they can't click things twice
        self.attributes("-disabled", True)

        # 2. Show the "Wrapping up" message overlay
        self.show_closing_dialog()

        # 3. Start the heavy lifting in a NEW thread
        #    (This keeps the UI responsive so the message renders)
        threading.Thread(target=self._run_shutdown_tasks, daemon=True).start()

    def show_closing_dialog(self):
        """Creates a simple, borderless message centered on the app."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("")
        dialog.overrideredirect(True)  # Removes the title bar/X button
        dialog.attributes("-topmost", True)

        w, h = 300, 120
        x = self.winfo_x() + (self.winfo_width() // 2) - (w // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (h // 2)
        dialog.geometry(f"{w}x{h}+{x}+{y}")

        frame = ctk.CTkFrame(dialog, corner_radius=10)
        frame.pack(fill="both", expand=True)

        ctk.CTkLabel(frame, text="Closing Application", font=ui_font(16, "bold")).pack(pady=(20, 5))
        ctk.CTkLabel(frame, text="Cleaning up temporary files...", font=ui_font(12)).pack(pady=5)

    def _run_shutdown_tasks(self):
        """Background thread: tear down without freezing the closing dialog.

        The GPU driver reclaims VRAM whenever the process actually dies, so the thing
        that matters here is that the process always dies - hence the watchdog at the end.
        """
        try:
            # Downloads first, and without waiting: they are sockets, and a stalled
            # one can take its full timeout to notice it has been told to stop.
            self.download_page.shutdown()

            self.queue_page.cancel_all()
            time.sleep(0.5)

            self.queue_page.release_gpu_if_idle()

            Util.force_delete_folder(global_vars.rec_folder, max_retries=20, delay=0.1)
        except Exception as e:
            log_runtime_error("Shutdown tasks failed", e)

        self.after(0, self._complete_exit)

        # Watchdog: if Tk is wedged the callback above never runs, and a hung process
        # keeps holding VRAM. Nothing after a successful _complete_exit gets here.
        time.sleep(5)
        os._exit(0)

    def _complete_exit(self):
        """Final step: actually kill the app."""
        try:
            self.destroy()
        finally:
            os._exit(0)
