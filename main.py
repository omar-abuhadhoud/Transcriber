import customtkinter as ctk
import threading
from tkinter import filedialog, messagebox
import os
import queue
import transcribe_module
import time
import traceback
import sys
from datetime import datetime
from media_item import MediaItem
from stopwatch import StopWatchLabel
import global_vars
from util import Util

# --- CONFIGURATION ---
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


def app_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.abspath(".")


def log_runtime_error(message, exc=None):
    log_dir = os.path.join(app_base_dir(), ".transcriptor_state", "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, "runtime.log")
    with open(log_path, "a", encoding="utf-8") as log_file:
        log_file.write("\n" + "=" * 72 + "\n")
        log_file.write(f"{datetime.now().isoformat(timespec='seconds')} - {message}\n")
        if exc is not None:
            log_file.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))

class TranscriptorQueueApp(ctk.CTk):
    def __init__(self):
        super().__init__()

       
        os.makedirs(global_vars.rec_folder, exist_ok=True)

        # --- WINDOW SETUP ---
        self.title("Transcriptor")
        self.iconbitmap(Util.resource_path("icon.ico"))
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
        self.bind("<Unmap>", self._on_minimize)
        self.bind("<Map>", self._on_restore)
     

    def start_worker_thread(self):
        self.worker_thread = threading.Thread(target=self.worker_loop, daemon=True)
        self.worker_thread.start()

    def _on_minimize(self, event):
        """Pause UI updates when minimized to reduce lag on restore"""
        # Stop updating progress bars while minimized
        pass

    def _on_restore(self, event):
        """Resume UI updates when restored"""
        # Force a single refresh after restore instead of recalculating everything
        if self.items:
            self.after(100, self.update_total_progress)




    def update_total_duration_label(self):
        self.lbl_total_duration.configure(text=f'Total Duration: {Util.format_duration(self.total_duration)}')

    
    def add_files(self):
        file_paths = filedialog.askopenfilenames(filetypes=[("Media Files", "*.mp3 *.mp4 *.wav *.m4a *.mkv")])
        for path in file_paths:
            item = MediaItem(self.scroll_area, path, self,on_delete_click=self.delete_item)
            item.pack(fill="x", pady=2, padx=5)
            self.items.append(item)
            self.total_duration=self.total_duration+item.durationInSeconds
            self.update_total_duration_label()
            self.progress_bar.pack(side="left", fill="x", expand=True, padx=5)
            self.update_total_progress()

            

    # --- QUEUE MANAGEMENT ---
    def add_to_queue(self, media_item):
        self.job_queue.put(media_item)

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
        """Background thread: Handles logic that was previously freezing the UI."""
        
        # --- YOUR LOGIC ADAPTED FOR THREADING ---
        
        # 1. Stop threads
        self.stop_all()
        
        # 2. Give threads time to react
        #    NOTE: We replaced your 'self.update()' loop with a simple sleep.
        #    Since this is a background thread, the Main UI thread is already 
        #    running free, so we don't need to manually pump it with update().
        time.sleep(0.5) 

        # 3. Nuke the folder (This was the main cause of the lag)
        #    Now it runs in the background while the UI says "Wrapping up"
        Util.force_delete_folder(global_vars.rec_folder, max_retries=20, delay=0.1)

        # 4. Trigger the actual exit on the main thread
        self.after(0, self._complete_exit)

    def _complete_exit(self):
        """Final step: actually kill the app."""
        self.destroy()
        os._exit(0)

    def update_total_progress(self):
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
                current_item.lbl_stopwatch.start()

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
                current_item.lbl_stopwatch.stop()
            except Exception as e:
                log_runtime_error("Queue worker failed", e)
                print(f"Queue Error: {e}")
                time.sleep(1)

if __name__ == "__main__":
    app = TranscriptorQueueApp()
    app.mainloop()
