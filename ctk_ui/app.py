import customtkinter as ctk
import threading
from tkinter import filedialog, messagebox
import os
import queue
import time
import traceback
import sys
from datetime import datetime
from transcriber import transcribe_module
from transcriber import registry
from transcriber.paths import resource_path
from transcriber.speed import evaluate_tiers, get_total_vram_gb
from transcriber.version import __version__
from ctk_ui.media_item import MediaItem
from ctk_ui.speed_picker import SpeedPicker
from ctk_ui.stopwatch import StopWatchLabel
import global_vars
from transcriber.util import Util

# --- CONFIGURATION ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


def app_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(".")


def log_runtime_error(message, exc=None):
    log_dir = os.path.join(app_base_dir(), ".transcriber_state", "logs")
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
        self.minsize(600, 400)
        self.grid_rowconfigure(1, weight=1) # Scroll area expands
        self.grid_columnconfigure(0, weight=1)

             # --- VARIABLES ---
        self.items = []
        self.job_queue = queue.Queue()
        self.total_duration=0


        # --- 1. HEADER ---
        self.header_frame = ctk.CTkFrame(self)
        self.header_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=10)

        # 1. Add Button (Fixed width, Left side)
        self.btn_add = ctk.CTkButton(
            self.header_frame,
            text="+ Add Media Files",
            command=self.add_files,
            font=("Arial", 13, "bold"),
            width=140,
            height=35
        )
        self.btn_add.pack(side="left", padx=(0, 15))

        # 1b. Engine picker. Switching is only allowed while the queue is idle, so a
        # run never spans two models.
        self.engine_labels = [label for _, label in registry.list_engines()]
        self.engine_menu = ctk.CTkOptionMenu(
            self.header_frame,
            values=self.engine_labels,
            command=self.on_engine_selected,
            width=190,
            height=35,
            font=("Arial", 12),
        )
        self.engine_menu.set(registry.label_for(registry.active_engine_name()))
        self.engine_menu.pack(side="left", padx=(0, 8))

        # 1c. Speed picker. Tiers this GPU cannot afford are disabled, not hidden.
        self.speed_picker = SpeedPicker(self.header_frame, on_change=self.on_speed_selected)
        self.speed_picker.pack(side="left", padx=(0, 15))
        self.refresh_speed_tiers()

        # 4. Total Duration Label (Fixed width, Far Right)
        formatted_time = Util.format_duration(self.total_duration)
        self.lbl_total_duration = ctk.CTkLabel(
            self.header_frame,
            text=f'Total: {formatted_time}',
            text_color="gray",
            font=("Arial", 12)
        )
        self.lbl_total_duration.pack(side="right", padx=(20, 0))

        # 3. Counter Label (e.g., "12/50") - Fixed width, Right of bar
        self.lbl_progress_count = ctk.CTkLabel(
            self.header_frame,
            text="",
            font=("Arial", 12, "bold"),
            text_color=("gray10", "gray90") # Adaptive color for light/dark mode
        )
        self.lbl_progress_count.pack(side="right", padx=(5, 15))

        # 2. Progress Bar (Flexible width, Middle - fills remaining space)
        self.progress_bar = ctk.CTkProgressBar(self.header_frame, height=12)
        self.progress_bar.pack(side="left", fill="x", expand=True, padx=5)
        self.progress_bar.pack_forget()  # Hide initially

        self.progress_bar.set(0) # Start empty



        # --- 2. SCROLLABLE QUEUE AREA ---
        self.scroll_area = ctk.CTkScrollableFrame(self, label_text="Transcription Queue")
        self.scroll_area.grid(row=1, column=0, sticky="nsew", padx=20, pady=5)
        self.scroll_area.grid_columnconfigure(0, weight=1) # Items expand width

        # --- 3. GLOBAL FOOTER ---
        self.footer = ctk.CTkFrame(self)
        self.footer.grid(row=2, column=0, sticky="ew", padx=20, pady=20)

        self.btn_save_all = ctk.CTkButton(self.footer, text="Save All Finished", command=self.save_all_finished)
        self.btn_save_all.pack(side="left", padx=10, pady=10)

        self.btn_stop_all = ctk.CTkButton(self.footer, text="Stop All", command=self.stop_all, fg_color="#c0392b")
        self.btn_stop_all.pack(side="right", padx=10)

        self.btn_start_all = ctk.CTkButton(self.footer, text="Start All Pending", command=self.start_all_pending, fg_color="green")
        self.btn_start_all.pack(side="right", padx=10)



        # Start the background worker
        self.start_worker_thread()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Optimize window state changes
        self.bind("<Map>", self._on_restore)


    def start_worker_thread(self):
        self.worker_thread = threading.Thread(target=self.worker_loop, daemon=True)
        self.worker_thread.start()

    def _on_restore(self, event):
        """Refresh once after the window is restored.

        <Map> also fires for every child widget, and each row adds a dozen of them, so
        without this guard adding files schedules hundreds of full-queue refreshes.
        """
        if event.widget is not self:
            return
        if self.items:
            self.after(100, self.update_total_progress)




    def update_total_duration_label(self):
        self.lbl_total_duration.configure(text=f'Total Duration: {Util.format_duration(self.total_duration)}')


    def add_files(self):
        file_paths = filedialog.askopenfilenames(filetypes=[("Media Files", "*.mp3 *.mp4 *.wav *.m4a *.mkv")])
        if not file_paths:
            return

        for path in file_paths:
            item = MediaItem(self.scroll_area, path, self,on_delete_click=self.delete_item)
            item.pack(fill="x", pady=2, padx=5)
            self.items.append(item)
            self.total_duration=self.total_duration+item.durationInSeconds

        # Refreshed once for the whole selection: these scan every row, so doing it per
        # file makes adding N files cost O(N^2).
        self.update_total_duration_label()
        self.progress_bar.pack(side="left", fill="x", expand=True, padx=5)
        self.update_total_progress()



    # --- ENGINE AND SPEED SELECTION ---
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
        except Exception as e:
            log_runtime_error(f"Could not select speed '{tier_name}'", e)
            messagebox.showerror("Speed", f"Could not change speed:\n{e}")
            self.refresh_speed_tiers()

    def on_engine_selected(self, label):
        name = registry.name_for_label(label)
        if name == registry.active_engine_name():
            return

        try:
            registry.set_engine(name)
            self.refresh_speed_tiers()
        except Exception as e:
            log_runtime_error(f"Could not switch to engine '{name}'", e)
            messagebox.showerror("Engine", f"Could not switch engine:\n{e}")
            self.engine_menu.set(registry.label_for(registry.active_engine_name()))

    def queue_is_busy(self):
        return any(item.state in ["waiting", "processing", "stopping"] for item in self.items)

    def update_engine_menu_state(self):
        if not self.engine_menu.winfo_exists(): return
        idle = not self.queue_is_busy()
        self.engine_menu.configure(state="normal" if idle else "disabled")
        self.speed_picker.set_enabled(idle)

    # --- QUEUE MANAGEMENT ---
    def add_to_queue(self, media_item):
        self.job_queue.put(media_item)
        self.update_engine_menu_state()

    def start_all_pending(self):
        for item in self.items:
            if item.state in ["idle", "stopped", "error"]:
                item.request_start()

    def stop_all(self):
        # Mark all items to stop
        for item in self.items:
            if item.state in ["waiting", "processing"]:
                item.request_stop()

    def save_all_finished(self):
        done_items = [i for i in self.items if i.state == "done"]
        if not done_items:
            messagebox.showinfo("Info", "No finished items to save.")
            return

        folder = filedialog.askdirectory(title="Select Folder to Save All Transcripts")
        if folder:
            count = 0
            for item in done_items:
                if os.path.exists(item.recovery_file):
                    name = f"{os.path.splitext(item.filename)[0]}.txt"
                    path = os.path.join(folder, name)
                    try:
                        with open(item.recovery_file, "r", encoding="utf-8") as src, open(path, "w", encoding="utf-8") as dst:
                            dst.write(src.read())
                        count += 1
                    except: pass
            messagebox.showinfo("Success", f"Saved {count} files to {folder}")



    def delete_item(self, item_to_remove):
        """
        Removes the item.
        """
        if item_to_remove in self.items:
            self.total_duration=self.total_duration-item_to_remove.durationInSeconds
            self.update_total_duration_label()
            self.items.remove(item_to_remove)
            item_to_remove.pack_forget() # Hide immediately so it looks deleted
            item_to_remove.request_stop()
            item_to_remove.destroy()
            self.after(0, self.update_total_progress)
        else: print("item is not found in items")

    def delete_recovery_file(self,item):
        if os.path.exists(item.recovery_file):
            try:
                os.remove(item.recovery_file)
                print('deleted')
            except Exception as e:
                print(f"Failed to delete: {e}")

    def remove_from_list(self, item_to_remove):
        if item_to_remove in self.items:
            self.items.remove(item_to_remove)

    # [ADD THIS NEW METHOD]

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
        dialog.overrideredirect(True) # Removes the title bar/X button
        dialog.attributes("-topmost", True)

        # Dimensions
        w, h = 300, 120

        # Center logic
        x = self.winfo_x() + (self.winfo_width() // 2) - (w // 2)
        y = self.winfo_y() + (self.winfo_height() // 2) - (h // 2)
        dialog.geometry(f"{w}x{h}+{x}+{y}")

        # Styling - Matches your "not a loading ring" request
        # Just a clean message telling them what is happening
        frame = ctk.CTkFrame(dialog, corner_radius=10)
        frame.pack(fill="both", expand=True)

        label_title = ctk.CTkLabel(frame, text="Closing Application", font=("Arial", 16, "bold"))
        label_title.pack(pady=(20, 5))

        label_status = ctk.CTkLabel(frame, text="Cleaning up temporary files...", font=("Arial", 12))
        label_status.pack(pady=5)
    def _run_shutdown_tasks(self):
        """Background thread: tear down without freezing the closing dialog.

        The GPU driver reclaims VRAM whenever the process actually dies, so the thing
        that matters here is that the process always dies - hence the watchdog at the end.
        """
        try:
            self.stop_all()
            time.sleep(0.5)

            # A run still inside generate() cannot be interrupted, and pulling the model
            # out from under it would crash rather than free anything. The forced exit
            # below hands the VRAM back in that case.
            if not any(item.state == "processing" for item in self.items):
                try:
                    transcribe_module.release_all_memory()
                except Exception as e:
                    log_runtime_error("Releasing GPU memory during shutdown failed", e)

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

    def update_total_progress(self):
        self.update_engine_menu_state()
        totalCount=len(self.items)
        if totalCount==0:
            self.lbl_progress_count.configure(text="")
            self.progress_bar.pack_forget()
            return
        doneCount=sum([1 for x in self.items if x.state=="done"])
        percentage=doneCount/totalCount
        self.progress_bar.set(percentage)
        self.lbl_progress_count.configure(text=f"{doneCount}/{totalCount}")


    class UserCancelled(Exception):
        pass

    def worker_loop(self):
        while True:
            try:

                # 1. Get next job
                current_item = self.job_queue.get()

                # ... (your existing setup code) ...

                if current_item.cancel_flag:
                    # ... (your existing skip logic) ...
                    self.job_queue.task_done()
                    continue

                self.after(0, lambda target=current_item: target.update_status("Processing...", "processing"))
                # Tk is not thread safe: the stopwatch schedules its own after() loop, so
                # it has to be started on the main thread, not from this worker.
                self.after(0, current_item.lbl_stopwatch.start)

                try:
                    with open(current_item.recovery_file, "w", encoding="utf-8") as f:

                        # --- CHANGE 1: Force stop in on_progress ---
                        def on_progress(percent, chunk_text):
                            if current_item.cancel_flag:
                                raise self.UserCancelled()  # <--- CRITICAL: Abort immediately!

                            if chunk_text:
                                f.write(chunk_text + " ")
                                f.flush()
                            self.after(0, lambda target=current_item: target.on_progress(percent, chunk_text))

                        # --- CHANGE 2: Force stop in check_cancel ---
                        def check_cancel():
                            if current_item.cancel_flag:
                                raise self.UserCancelled()  # <--- CRITICAL: Abort immediately!
                            return False

                        def on_status(message):
                            self.after(0, lambda target=current_item, text=message: target.update_status(text, "processing"))

                        transcribe_module.run_transcription(
                            current_item.file_path,
                            progress_callback=on_progress,
                            status_callback=on_status,
                            check_cancel=check_cancel
                        )

                    # If we get here, it finished successfully
                    self.after(0, lambda target=current_item: target.finish_success())
                    self.after(0, self.update_total_progress)

                # --- CHANGE 3: Catch the forced stop ---
                except self.UserCancelled:
                    # This block runs INSTANTLY when you raise the exception above

                    self.delete_recovery_file(current_item)
                    self.after(0, lambda target=current_item: target.finish_stopped())

                except Exception as e:
                    self.delete_recovery_file(current_item)
                    log_runtime_error(f"Transcription failed for {current_item.file_path}", e)
                    self.after(0, lambda target=current_item: target.finish_error(str(e)))
                    self.after(0, self.update_total_progress)

                self.job_queue.task_done()
                self.after(0, current_item.lbl_stopwatch.stop)
                self.after(0, self.update_engine_menu_state)

                # Only once nothing is left to run: between files the warm allocator
                # cache is worth keeping, but an idle app should not sit on spare VRAM.
                if self.job_queue.empty():
                    transcribe_module.release_idle_memory()
            except Exception as e:
                log_runtime_error("Queue worker failed", e)
                print(f"Queue Error: {e}")
                time.sleep(1)
