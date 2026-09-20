import customtkinter as ctk

from ctk_ui.theme import ui_font
from tkinter import filedialog, messagebox
import itertools
import os
from transcriber.util import Util
import global_vars
import tempfile
from ctk_ui.stopwatch import StopWatchLabel

class CancelToken:
    """The cancellation of one run.

    A token per run rather than a flag on the row, because a cancelled run can still
    be unwinding when the row is started again, and clearing a flag those two runs
    share would quietly un-cancel the first one.
    """

    __slots__ = ("cancelled",)

    def __init__(self):
        self.cancelled = False


class MediaItem(ctk.CTkFrame):
    """
    Represents a single row in the scrollable list.
    """
    # Hands out the suffix that keeps two rows' recovery files apart. itertools.count
    # is used rather than a plain int because next() on it is atomic, so this holds
    # even if a row is ever built off the main thread.
    _recovery_seq = itertools.count(1)

    def __init__(self, parent, file_path, app_manager, on_delete_click=None,
                 known_duration=None):
        super().__init__(parent)
        self.app = app_manager
        self.file_path = file_path
        self.on_delete_click=on_delete_click
        self.filename = os.path.basename(file_path)
        self.state = "idle"  # idle, waiting, processing, done, error, cancelled
        # Bumped every time this row starts or is cancelled. The worker carries the
        # value it started with, so a callback from a run that has been abandoned
        # cannot land on a row that has since been started again.
        self.run_id = 0
        # Replaced, never cleared: see CancelToken.
        self.cancel_token = CancelToken()
        # A download already knows the duration from the post's own metadata, so the
        # file is not reopened just to measure something the platform already told us.
        if known_duration:
            self.durationInSeconds = known_duration
        else:
            self.durationInSeconds = Util.get_audio_duration(self.file_path)
        # One recovery file per row, keyed on a counter rather than on the file name.
        # The same name reaches the queue whenever two folders hold an interview.mp3,
        # or the same file is added twice, and the worker opens this path with "w":
        # a shared name would truncate the first row's transcript and then hand it
        # back for that row's Copy and Save. The name is kept in the filename only so
        # that a file left behind by a crash is still identifiable by eye.
        stem = os.path.splitext(self.filename)[0]
        safe_stem = "".join(c for c in stem if c.isalnum() or c in " -_").strip()
        self.recovery_file = os.path.join(
            global_vars.rec_folder,
            "{0}_{1}.txt".format(safe_stem[:60] or "audio", next(MediaItem._recovery_seq)),
        )

        # --- UI LAYOUT ---
        # Use pack for top section (faster than grid)
        top_frame = ctk.CTkFrame(self, fg_color="transparent")
        top_frame.pack(fill="x", padx=5, pady=5)
        
        # Left section
        left_frame = ctk.CTkFrame(top_frame, fg_color="transparent")
        left_frame.pack(side="left", fill="both", expand=True)
        
        # 1. Filename
        self.lbl_name = ctk.CTkLabel(left_frame, text=self.filename, anchor="w", font=ui_font(12, "bold"))
        self.lbl_name.pack(anchor="w", padx=5)
        
        # 2. Duration
        self.lbl_duration = ctk.CTkLabel(left_frame, text=Util.format_duration(self.durationInSeconds), text_color="gray", font=ui_font(11))
        self.lbl_duration.pack(anchor="w", padx=5, pady=(2, 0))
    
        # Right section (status + stopwatch)
        right_frame = ctk.CTkFrame(top_frame, fg_color="transparent")
        right_frame.pack(side="right", padx=5)
        
        self.lbl_status = ctk.CTkLabel(right_frame, text="Idle", text_color="gray", font=ui_font(11))
        self.lbl_status.pack(anchor="e")
        
        self.lbl_stopwatch=StopWatchLabel(right_frame)
        self.lbl_stopwatch.pack(anchor="e", pady=(2, 0))

        # 3. Progress Bar
        self.progress_bar = ctk.CTkProgressBar(self, height=8)
        self.progress_bar.pack(fill="x", padx=10, pady=(0, 5))
        self.progress_bar.set(0)

        # 4. Buttons
        self.btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.btn_frame.pack(fill="x", padx=5, pady=(0, 5))

        # Pack buttons from right to left for better visual balance
        # The X cancels and removes in one press, whatever the row is doing. There is
        # no separate stop: a run nobody wants is a run nobody wants, and asking
        # first only keeps the GPU busy for the length of the question.
        self.btn_delete = ctk.CTkButton(self.btn_frame, text="X", width=30, height=30,
                                        command=self._handle_delete_click, fg_color="#7f8c8d", hover_color="#95a5a6")
        self.btn_delete.pack(side="right", padx=2)

        self.btn_save = ctk.CTkButton(self.btn_frame, text="Save", width=50, height=30, 
                                      command=self.save_text, state="disabled")
        self.btn_save.pack(side="right", padx=2)

        self.btn_copy = ctk.CTkButton(self.btn_frame, text="Copy", width=50, height=30, 
                                      command=self.copy_text, state="disabled")
        self.btn_copy.pack(side="right", padx=2)

        self.btn_view = ctk.CTkButton(
            self.btn_frame, 
            text="👁",           # The Eye Icon
            width=40,            # Make it square/small
            font=ui_font(20), state="disabled", command=self.open_in_word_rtl
        )
        self.btn_view.pack(side="right", padx=2)

        self.btn_start = ctk.CTkButton(self.btn_frame, text="▶", width=30, height=30, 
                                       command=self.request_start, fg_color="green")
        self.btn_start.pack(side="right", padx=2)



 


    def open_in_word_rtl(self):
        text = self._read_transcript()
        if text is None:
            return
    # 1. Prepare RTF Header for Arabic (RTL) Support
    # \rtf1 = RTF format
    # \ansi = Character set
    # \deflang1025 = Arabic (Saudi Arabia) default language ID
        header = r"{\rtf1\ansi\ansicpg1252\deff0\nouicompat\deflang1025" \
                r"{\fonttbl{\f0\fnil\fcharset178 Arial;}}" \
                r"\viewkind4\uc1"

        # 2. Configure Paragraph: RTL Direction + Right Alignment
        # \pard = Reset paragraph
        # \rtlpar = Right-to-Left Direction (Critical for Arabic)
        # \qr = Right Align
        # \f0\fs32 = Arial Font, Size 16
        formatting = r"\pard\sa200\sl276\slmult1\rtlpar\qr\lang1025\f0\fs32 "

        # 3. Encode Text to RTF-safe format
        # This loop ensures every Arabic character is readable by Word
        safe_text = ""
        for char in text:
            code = ord(char)
            if code > 127:
                safe_text += f"\\u{code}?" # Unicode escape
            elif char == "\n":
                safe_text += "\\par "      # New line
            elif char in ["{", "}", "\\"]:
                safe_text += "\\" + char   # Escape special chars
            else:
                safe_text += char

        # 4. Combine parts
        full_content = header + formatting + safe_text + "}"

        # 5. Create a standard Temporary File (Invisible to your project)
        # This creates a file in C:\Users\You\AppData\Local\Temp\...
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.rtf', encoding='utf-8') as temp:
            temp.write(full_content)
            temp_path = temp.name

        # 6. Open immediately in Word
        os.startfile(temp_path)

    def _handle_delete_click(self):
        if self.on_delete_click:
            self.on_delete_click(self)

    
    # --- METHODS THAT WERE MISSING ---
    def request_start(self):
        if self.state in ["processing", "waiting"]: return
        self.reset_ui()
        self.run_id += 1
        self.app.add_to_queue(self)
        self.update_status("Waiting...", "waiting")
        self.btn_start.configure(state="disabled")

    def cancel_now(self):
        """Abandon whatever this row is doing, this instant.

        The token is what the worker and the engine poll, and they do it often enough
        that nothing waits for a chunk to finish. Bumping run_id retires the run at
        the same time, so anything it still reports is ignored.
        """
        self.cancel_token.cancelled = True
        self.run_id += 1
        self.lbl_stopwatch.stopAndReset()

    @property
    def is_cancelled(self):
        return self.cancel_token.cancelled

    def request_cancel(self):
        """Cancel, and leave the row at rest so it can be started again."""
        was_active = self.state in ["waiting", "processing"]
        self.cancel_now()

        if not was_active or not self.winfo_exists():
            return
        self.update_status("Cancelled", "cancelled")
        self.progress_bar.set(0)
        self.btn_start.configure(state="normal")


        
    def update_status(self, text, state_code):
        if not self.winfo_exists(): return # [ADD THIS LINE]
        self.state = state_code
        self.lbl_status.configure(text=text)
        if state_code == "done": self.lbl_status.configure(text_color="#2ecc71")
        elif state_code == "error": self.lbl_status.configure(text_color="#e74c3c")
        elif state_code == "processing": self.lbl_status.configure(text_color="#3498db")
        else: self.lbl_status.configure(text_color="gray")

    def reset_ui(self):
        self.progress_bar.set(0)
        self.cancel_token = CancelToken()
        self.btn_copy.configure(state="disabled")
        self.btn_save.configure(state="disabled")
        

    def on_progress(self, percent, chunk_text):
        if not self.winfo_exists(): return
        self.progress_bar.set(percent)
        self.lbl_status.configure(text=f"Processing {int(percent*100)}%")

    def finish_success(self):
        self.progress_bar.set(1)
        self.update_status("Completed", "done")
        self.btn_start.configure(state="disabled")

        self.btn_view.configure(state="normal")
        self.btn_copy.configure(state="normal")
        self.btn_save.configure(state="normal")

    def finish_cancelled(self):
        """The worker finished unwinding a run that was cancelled."""
        if not self.winfo_exists(): return
        self.update_status("Cancelled", "cancelled")
        self.progress_bar.set(0)
        self.btn_start.configure(state="normal")

    def finish_error(self, err_msg):
        short_msg = err_msg if len(err_msg) <= 180 else err_msg[:177] + "..."
        self.update_status(f"Error: {short_msg}", "error")
        self.btn_start.configure(state="normal")

    def _read_transcript(self):
        """The transcript as it was written to disk, or None once the user has been told.

        This file is the only copy of the transcript, so a failure to read it is the
        difference between the user getting their text and losing it. It is never
        swallowed: the old silent return left Copy and Save looking like dead buttons.
        Opening is attempted directly rather than checked with exists() first, so that
        a file deleted between the two, or one that cannot be opened for some other
        reason, ends up on the same path.
        """
        try:
            with open(self.recovery_file, "r", encoding="utf-8") as handle:
                return handle.read()
        except OSError as exc:
            self.app.log_error("Could not read the transcript for " + self.filename, exc)
            messagebox.showerror(
                "Transcript unavailable",
                "The transcript for {0} could not be read.\n\n{1}\n\n"
                "Transcribing the file again will rebuild it.".format(self.filename, exc),
            )
            return None

    def copy_text(self):
        text = self._read_transcript()
        if text is None:
            return
        try:
            self.app.clipboard_clear()
            self.app.clipboard_append(text)
            self.app.update() # Keeps clipboard ready
            
            # 3. Save Original Button Style (so we can restore it)
            
            orig_text = "Copy"
            orig_color = self.btn_copy.cget("fg_color")
            orig_hover = self.btn_copy.cget("hover_color")

            # 4. Transform to "Success" State (Green + Check)
            self.btn_copy.configure(
                text="✔ Copied", 
                fg_color="#2ecc71",   # Green
                hover_color="#27ae60", # Darker Green
                text_color="white"
            )

            # 5. Schedule the Revert (3 seconds later)
            def revert_style():
                if self.winfo_exists(): # Safety check in case item was deleted
                    self.btn_copy.configure(
                        text=orig_text, 
                        fg_color=orig_color, 
                        hover_color=orig_hover,
                        text_color=["#DCE4EE", "#DCE4EE"] # Default CTk text color
                    )
            
            self.after(1500, revert_style)

        except Exception as exc:
            self.app.log_error("Could not copy the transcript for " + self.filename, exc)
            messagebox.showerror(
                "Copy failed",
                "The transcript could not be put on the clipboard.\n\n{0}".format(exc),
            )

    def save_text(self):
        text = self._read_transcript()
        if text is None:
            return
        default_name = f"{os.path.splitext(self.filename)[0]}_transcript.txt"
        save_path = filedialog.asksaveasfilename(defaultextension=".txt", initialfile=default_name)
        if not save_path:
            return
        try:
            with open(save_path, "w", encoding="utf-8") as dst:
                dst.write(text)
        except OSError as exc:
            # A read-only folder or a name the filesystem rejects used to escape into
            # Tk's callback handler, where the user sees nothing at all.
            self.app.log_error("Could not save the transcript to " + str(save_path), exc)
            messagebox.showerror(
                "Save failed",
                "{0} could not be written.\n\n{1}".format(save_path, exc),
            )
