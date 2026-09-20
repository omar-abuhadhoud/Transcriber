"""The transcription queue: everything the app was before there was a second tab.

This used to be the window itself. It is a frame now so that a download can be going
on beside it, but nothing about how transcription works has changed: one worker
thread, one file at a time, because there is one GPU and a second concurrent run would
simply run out of VRAM.

The download pool on the other tab is deliberately unrelated to this. It never imports
torch and never opens a CUDA context, so downloads and transcription cannot contend
for the one resource that matters.
"""

import os
import queue
import threading
import time
from tkinter import filedialog, messagebox

import customtkinter as ctk

from ctk_ui import theme
from ctk_ui.media_item import MediaItem
from ctk_ui.speed_picker import SpeedPicker
from ctk_ui.theme import ui_font
from transcriber import registry, transcribe_module
from transcriber.speed import evaluate_tiers
from transcriber.util import Util

# Containers the queue accepts, now that downloads add m4a, opus and webm alongside
# whatever the user picks by hand.
MEDIA_TYPES = [
    ("Media Files", "*.mp3 *.mp4 *.wav *.m4a *.mkv *.webm *.opus *.ogg *.flac *.aac *.mov"),
    ("All Files", "*.*"),
]


class UserCancelled(Exception):
    """Raised inside the worker to abandon a run the moment it is cancelled."""


class QueuePage(ctk.CTkFrame):
    """Header, the list of files, and the footer of bulk actions."""

    def __init__(self, parent, log_error, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)

        self.log_error = log_error
        self.items = []
        self.job_queue = queue.Queue()
        self.total_duration = 0
        # The item the worker is inside right now, or None. Written by the worker and
        # read by the UI: a row can be cancelled and removed from self.items while its
        # run is still unwinding, and until it has, the model must not be pulled out
        # from under it.
        self.running_item = None

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._build_header()
        self._build_list()
        self._build_footer()

        self.start_worker_thread()

    # ------------------------------------------------------------------- building

    def _build_header(self):
        self.header_frame = ctk.CTkFrame(self)
        self.header_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=10)

        self.btn_add = ctk.CTkButton(
            self.header_frame,
            text="+ Add Media Files",
            command=self.add_files,
            font=ui_font(13, "bold"),
            width=140,
            height=35,
        )
        self.btn_add.pack(side="left", padx=(0, 15))

        # Engine picker. Switching is only allowed while the queue is idle, so a run
        # never spans two models.
        self.engine_labels = [label for _, label in registry.list_engines()]
        self.engine_menu = theme.option_menu(
            self.header_frame,
            values=self.engine_labels,
            command=self.on_engine_selected,
        )
        self.engine_menu.set(registry.label_for(registry.active_engine_name()))
        self.engine_menu.pack(side="left", padx=(0, 8))

        # Speed picker. Tiers this GPU cannot afford are disabled, not hidden.
        self.speed_picker = SpeedPicker(self.header_frame, on_change=self.on_speed_selected)
        self.speed_picker.pack(side="left", padx=(0, 15))
        self.refresh_speed_tiers()

        self.lbl_total_duration = ctk.CTkLabel(
            self.header_frame,
            text="Total: " + Util.format_duration(self.total_duration),
            text_color=theme.MUTED,
            font=ui_font(12),
        )
        self.lbl_total_duration.pack(side="right", padx=(20, 0))

        self.lbl_progress_count = ctk.CTkLabel(
            self.header_frame,
            text="",
            font=ui_font(12, "bold"),
            text_color=("gray10", "gray90"),
        )
        self.lbl_progress_count.pack(side="right", padx=(5, 15))

        self.progress_bar = ctk.CTkProgressBar(self.header_frame, height=12)
        self.progress_bar.pack(side="left", fill="x", expand=True, padx=5)
        self.progress_bar.pack_forget()
        self.progress_bar.set(0)

    def _build_list(self):
        self.scroll_area = ctk.CTkScrollableFrame(self, label_text="Transcription Queue")
        self.scroll_area.grid(row=1, column=0, sticky="nsew", padx=20, pady=5)
        self.scroll_area.grid_columnconfigure(0, weight=1)

    def _build_footer(self):
        self.footer = ctk.CTkFrame(self)
        self.footer.grid(row=2, column=0, sticky="ew", padx=20, pady=(5, 14))

        self.btn_save_all = ctk.CTkButton(
            self.footer, text="Save All Finished", command=self.save_all_finished
        )
        self.btn_save_all.pack(side="left", padx=10, pady=10)

        self.btn_cancel_all = ctk.CTkButton(
            self.footer, text="Cancel All", command=self.cancel_all, fg_color=theme.DANGER
        )
        self.btn_cancel_all.pack(side="right", padx=10)

        self.btn_start_all = ctk.CTkButton(
            self.footer, text="Start All Pending", command=self.start_all_pending,
            fg_color="green"
        )
        self.btn_start_all.pack(side="right", padx=10)

    # --------------------------------------------------------------- adding files

    def add_files(self):
        file_paths = filedialog.askopenfilenames(filetypes=MEDIA_TYPES)
        if not file_paths:
            return

        for path in file_paths:
            self._append_item(path)

        # Refreshed once for the whole selection: these scan every row, so doing it
        # per file makes adding N files cost O(N^2).
        self.update_total_duration_label()
        self.progress_bar.pack(side="left", fill="x", expand=True, padx=5)
        self.update_total_progress()

    def add_downloaded(self, result):
        """Put a freshly downloaded file into the queue, at rest.

        Nothing starts by itself. A download finishing is not a decision to occupy the
        GPU, and the queue's own Start buttons remain the only thing that does that.
        """
        item = self._append_item(result.path, known_duration=result.duration)
        self.update_total_duration_label()
        self.progress_bar.pack(side="left", fill="x", expand=True, padx=5)
        self.update_total_progress()
        return item

    def _append_item(self, path, known_duration=None):
        item = MediaItem(
            self.scroll_area,
            path,
            self,
            on_delete_click=self.delete_item,
            known_duration=known_duration,
        )
        item.pack(fill="x", pady=2, padx=5)
        self.items.append(item)
        self.total_duration += item.durationInSeconds
        return item

    def update_total_duration_label(self):
        self.lbl_total_duration.configure(
            text="Total Duration: " + Util.format_duration(self.total_duration)
        )

    # -------------------------------------------------- engine and speed selection

    def refresh_speed_tiers(self):
        """Recompute affordable tiers. Engines differ in weight size, so this runs per engine."""
        weights_gb = registry.weights_gb_for(registry.active_engine_name())
        statuses = evaluate_tiers(weights_gb)

        current = registry.active_tier_name()
        chosen = next((s for s in statuses if s.tier.name == current), None)
        if chosen is None or not chosen.available:
            # The tier that fit the previous engine may not fit this one.
            fallback = next((s for s in statuses if s.recommended), None)
            fallback = fallback or next((s for s in statuses if s.available), statuses[0])
            registry.set_speed(fallback.tier.name)
            current = fallback.tier.name

        self.speed_picker.set_statuses(statuses, current)

    def on_speed_selected(self, tier_name):
        try:
            registry.set_speed(tier_name)
        except Exception as exc:
            self.log_error("Could not select speed '" + str(tier_name) + "'", exc)
            messagebox.showerror("Speed", "Could not change speed:\n" + str(exc))
            self.refresh_speed_tiers()

    def on_engine_selected(self, label):
        name = registry.name_for_label(label)
        if name == registry.active_engine_name():
            return

        try:
            registry.set_engine(name)
            self.refresh_speed_tiers()
        except Exception as exc:
            self.log_error("Could not switch to engine '" + str(name) + "'", exc)
            messagebox.showerror("Engine", "Could not switch engine:\n" + str(exc))
            self.engine_menu.set(registry.label_for(registry.active_engine_name()))

    def queue_is_busy(self):
        # running_item covers the gap where a cancelled row has already left the list
        # but its run has not finished unwinding yet.
        if self.running_item is not None:
            return True
        return any(item.state in ["waiting", "processing"] for item in self.items)

    def update_engine_menu_state(self):
        if not self.engine_menu.winfo_exists():
            return
        idle = not self.queue_is_busy()
        self.engine_menu.configure(state="normal" if idle else "disabled")
        self.speed_picker.set_enabled(idle)

    # ----------------------------------------------------------- queue management

    def add_to_queue(self, media_item):
        self.job_queue.put(media_item)
        self.update_engine_menu_state()

    def start_all_pending(self):
        for item in self.items:
            if item.state in ["idle", "cancelled", "error"]:
                item.request_start()

    def cancel_all(self):
        """Give up on everything in flight and hand the working VRAM back.

        The model stays loaded. Cancelling is not a reason to make the next run pay
        for loading it again; what goes is what the run was using -- activations, the
        KV cache, the decoded chunks -- which is the part that grows with the queue.
        The rows stay too, at rest, so Start All Pending can pick them up again.
        """
        for item in list(self.items):
            if item.state in ["waiting", "processing"]:
                item.request_cancel()

        self.purge_cancelled_jobs()
        self.update_engine_menu_state()

        # A run still unwinding frees its own memory on the way out, and doing it from
        # here as well would mean two threads in the allocator at once.
        if self.running_item is None:
            self.release_working_memory()

    def release_working_memory(self):
        try:
            transcribe_module.release_working_memory()
        except Exception as exc:
            self.log_error("Releasing GPU working memory failed", exc)

    def purge_cancelled_jobs(self):
        """Drop cancelled items out of the pending queue.

        The worker skips them when their turn comes anyway, so this is about letting
        go now: while the queue holds an item it holds the row, the recovery path and
        everything hanging off them, for as long as the files ahead of it take.
        """
        kept = []
        while True:
            try:
                item = self.job_queue.get_nowait()
            except queue.Empty:
                break
            self.job_queue.task_done()
            if not item.is_cancelled:
                kept.append(item)

        for item in kept:
            self.job_queue.put(item)

    def save_all_finished(self):
        done_items = [i for i in self.items if i.state == "done"]
        if not done_items:
            messagebox.showinfo("Info", "No finished items to save.")
            return

        folder = filedialog.askdirectory(title="Select Folder to Save All Transcripts")
        if not folder:
            return

        count = 0
        failed = []
        taken = set()
        for item in done_items:
            name = os.path.splitext(item.filename)[0] + ".txt"
            # Per-row recovery files are no help if two rows then land on one output
            # name: two folders holding an interview.mp3 would leave one transcript
            # on disk, silently overwritten by the other.
            stem, ext = os.path.splitext(name)
            nth = 2
            while name.lower() in taken:
                name = "{0} ({1}){2}".format(stem, nth, ext)
                nth += 1
            taken.add(name.lower())

            path = os.path.join(folder, name)
            # A missing recovery file raises here rather than being skipped in silence,
            # so a transcript the user asked for never goes missing without a word.
            try:
                with open(item.recovery_file, "r", encoding="utf-8") as src, \
                        open(path, "w", encoding="utf-8") as dst:
                    dst.write(src.read())
                count += 1
            except OSError as exc:
                self.log_error("Could not save transcript for " + item.filename, exc)
                failed.append(item.filename)

        if failed:
            messagebox.showwarning(
                "Some transcripts were not saved",
                "Saved {0} of {1} to {2}.\n\nThese could not be written:\n{3}".format(
                    count, len(done_items), folder, "\n".join(failed[:10])),
            )
        else:
            messagebox.showinfo("Success", "Saved {0} files to {1}".format(count, folder))

    def delete_item(self, item_to_remove):
        """The X on a row: cancel and remove, in one press, with nothing to confirm.

        Instant in both directions. The row is gone from the list before this returns,
        and the run behind it is already abandoned: the engine sees the flag within a
        decoding step and frees what it was holding, the pending queue lets go of the
        item here, and the recovery file goes with it.
        """
        if item_to_remove not in self.items:
            return

        # Cancelled before anything else is read, so a worker that is picking this
        # item up right now sees the cancel rather than starting on it.
        item_to_remove.cancel_now()
        was_running = self.running_item is item_to_remove

        self.total_duration -= item_to_remove.durationInSeconds
        self.update_total_duration_label()
        self.items.remove(item_to_remove)
        item_to_remove.pack_forget()  # Hide immediately so it looks deleted
        item_to_remove.destroy()

        self.purge_cancelled_jobs()

        if not was_running:
            # The worker still has the recovery file of a run it is unwinding open,
            # and Windows will not unlink an open file; that run deletes its own.
            self.delete_recovery_file(item_to_remove)

        self.after(0, self.update_total_progress)

    def delete_recovery_file(self, item):
        if os.path.exists(item.recovery_file):
            try:
                os.remove(item.recovery_file)
            except OSError as exc:
                self.log_error("Could not delete recovery file " + item.recovery_file, exc)

    def remove_from_list(self, item_to_remove):
        if item_to_remove in self.items:
            self.items.remove(item_to_remove)

    def update_total_progress(self):
        self.update_engine_menu_state()
        total_count = len(self.items)
        if total_count == 0:
            self.lbl_progress_count.configure(text="")
            self.progress_bar.pack_forget()
            return

        done_count = sum(1 for x in self.items if x.state == "done")
        self.progress_bar.set(done_count / total_count)
        self.lbl_progress_count.configure(text="{0}/{1}".format(done_count, total_count))

    def refresh_after_restore(self):
        """Recompute once after the window is restored from the taskbar."""
        if self.items:
            self.after(100, self.update_total_progress)

    # ---------------------------------------------------------------- the worker

    def start_worker_thread(self):
        self.worker_thread = threading.Thread(target=self.worker_loop, daemon=True)
        self.worker_thread.start()

    def post_to_item(self, item, run_id, fn):
        """Run fn on the UI thread, unless the row has moved on without us.

        A cancelled run keeps reporting for as long as it takes to unwind, and by
        then the row may have been removed, or cancelled and started again. Either
        way its news is stale, and applying it would overwrite the newer run.
        """
        def apply():
            if item.winfo_exists() and item.run_id == run_id:
                fn()

        try:
            self.after(0, apply)
        except Exception:
            # The window is on its way out; there is nothing left to update.
            pass

    def worker_loop(self):
        while True:
            try:
                current_item = self.job_queue.get()
                run_id = current_item.run_id
                # Taken once, and polled through the run: the row's own token is
                # replaced the moment it is started again, and this run must keep
                # answering to the one it was started with.
                token = current_item.cancel_token

                if token.cancelled:
                    # Cancelled while it was still queued. Nothing ever started, so
                    # there is nothing to unwind and nothing to free.
                    self.job_queue.task_done()
                    continue

                self.running_item = current_item
                self.post_to_item(current_item, run_id, lambda target=current_item:
                                  target.update_status("Processing...", "processing"))
                # Tk is not thread safe: the stopwatch schedules its own after() loop,
                # so it has to be started on the main thread, not from this worker.
                self.post_to_item(current_item, run_id, current_item.lbl_stopwatch.start)

                cancelled = self._transcribe_one(current_item, run_id, token)

                self.running_item = None
                self.job_queue.task_done()
                self.post_to_item(current_item, run_id, current_item.lbl_stopwatch.stop)
                self.after(0, self.update_engine_menu_state)

                # After a cancel, because that is when someone is waiting for the
                # memory. Otherwise only once nothing is left to run: between files
                # the warm allocator cache is worth keeping, but an idle app should
                # not sit on spare VRAM.
                if cancelled or self.job_queue.empty():
                    transcribe_module.release_working_memory()
            except Exception as exc:
                self.log_error("Queue worker failed", exc)
                time.sleep(1)
            finally:
                # Whatever happened, this worker is no longer inside a run, and the
                # shutdown path reads this to decide whether it may unload the model.
                self.running_item = None

    def _transcribe_one(self, current_item, run_id, token):
        """Run one file. Returns True if it was cancelled rather than finished."""
        try:
            with open(current_item.recovery_file, "w", encoding="utf-8") as handle:

                def on_progress(percent, chunk_text):
                    if token.cancelled:
                        raise UserCancelled()  # Abort immediately, mid-file.

                    if chunk_text:
                        handle.write(chunk_text + " ")
                        handle.flush()
                    self.post_to_item(current_item, run_id, lambda target=current_item:
                                      target.on_progress(percent, chunk_text))

                def check_cancel():
                    if token.cancelled:
                        raise UserCancelled()
                    return False

                def on_status(message):
                    self.post_to_item(current_item, run_id,
                                      lambda target=current_item, text=message:
                                      target.update_status(text, "processing"))

                transcribe_module.run_transcription(
                    current_item.file_path,
                    progress_callback=on_progress,
                    status_callback=on_status,
                    check_cancel=check_cancel,
                )

            self.post_to_item(current_item, run_id, lambda target=current_item:
                              target.finish_success())
            self.after(0, self.update_total_progress)
            return False

        except UserCancelled:
            # The handle is closed by the time we get here, so the half-written
            # transcript can actually go; Windows would refuse while it was open.
            self.delete_recovery_file(current_item)
            self.post_to_item(current_item, run_id, lambda target=current_item:
                              target.finish_cancelled())
            self.after(0, self.update_total_progress)
            return True

        except Exception as exc:
            self.delete_recovery_file(current_item)
            self.log_error("Transcription failed for " + str(current_item.file_path), exc)
            self.post_to_item(current_item, run_id, lambda target=current_item, message=str(exc):
                              target.finish_error(message))
            self.after(0, self.update_total_progress)
            return False

    # ------------------------------------------------------------------ shutdown

    def release_gpu_if_idle(self):
        """Hand back VRAM, unless a run is still inside generate().

        A run that has not finished unwinding must not have the model pulled out from
        under it; that would crash rather than free anything. The caller's forced exit
        hands the memory back in that case.
        """
        if self.running_item is not None:
            return False
        try:
            transcribe_module.release_all_memory()
        except Exception as exc:
            self.log_error("Releasing GPU memory during shutdown failed", exc)
        return True
