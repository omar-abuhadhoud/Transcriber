import customtkinter as ctk
from tkinter import filedialog
import os
from transcriber.util import Util
import global_vars
import tempfile
from ctk_ui.stopwatch import StopWatchLabel

class MediaItem(ctk.CTkFrame):
    """
    Represents a single row in the scrollable list.
    """
    def __init__(self, parent, file_path, app_manager,on_delete_click=None):
        super().__init__(parent)
        self.app = app_manager
        self.file_path = file_path
        self.on_delete_click=on_delete_click
        self.filename = os.path.basename(file_path)
        self.transcription_text = ""
        self.state = "idle"  # idle, waiting, processing, done, error, stopped
        self.durationInSeconds=Util.get_audio_duration(self.file_path)
        # Create a unique recovery filename
        safe_name = "".join([c for c in self.filename if c.isalpha() or c.isdigit() or c==' ']).rstrip()
        self.recovery_file = f"recovery_{safe_name}.txt"

        safe_filename = os.path.basename(self.file_path) + ".txt"
        recovery_path = os.path.join(global_vars.rec_folder, safe_filename)
        
        # Store this path so we can reference it later if needed
        self.recovery_file = recovery_path

        # --- UI LAYOUT ---
        # Use pack for top section (faster than grid)
        top_frame = ctk.CTkFrame(self, fg_color="transparent")
        top_frame.pack(fill="x", padx=5, pady=5)
        
        # Left section
        left_frame = ctk.CTkFrame(top_frame, fg_color="transparent")
        left_frame.pack(side="left", fill="both", expand=True)
        
        # 1. Filename
        self.lbl_name = ctk.CTkLabel(left_frame, text=self.filename, anchor="w", font=("Arial", 12, "bold"))
        self.lbl_name.pack(anchor="w", padx=5)
        
        # 2. Duration
        self.lbl_duration = ctk.CTkLabel(left_frame, text=Util.format_duration(self.durationInSeconds), text_color="gray", font=("Arial", 11))
        self.lbl_duration.pack(anchor="w", padx=5, pady=(2, 0))
    
        # Right section (status + stopwatch)
        right_frame = ctk.CTkFrame(top_frame, fg_color="transparent")
        right_frame.pack(side="right", padx=5)
        
        self.lbl_status = ctk.CTkLabel(right_frame, text="Idle", text_color="gray", font=("Arial", 11))
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
        # [ADD THIS CODE] --- Delete Button ---
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
            font=("Arial", 20), state="disabled", command=self.open_in_word_rtl
        )
        self.btn_view.pack(side="right", padx=2)

        self.btn_stop = ctk.CTkButton(self.btn_frame, text="⏹", width=30, height=30, 
                                      command=self.request_stop, fg_color="#c0392b", state="disabled")
        self.btn_stop.pack(side="right", padx=2)

        self.btn_start = ctk.CTkButton(self.btn_frame, text="▶", width=30, height=30, 
                                       command=self.request_start, fg_color="green")
        self.btn_start.pack(side="right", padx=2)

        self.cancel_flag = False



 


    def open_in_word_rtl(self):
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
        for char in self.transcription_text:
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
        self.app.add_to_queue(self)
        self.update_status("Waiting...", "waiting")
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")

    def request_stop(self):
        self.cancel_flag = True
        if self.state == "waiting":
            # Safe to stop immediately because no thread is running
            
            self.update_status("Cancelled", "idle") 
            self.btn_start.configure(state="normal")
            self.btn_stop.configure(state="disabled")
            
        elif self.state == "processing":
            # DO NOT set state to "stopped" here!
            # Set it to "stopping" so delete_item knows to keep waiting.
            self.update_status("Stopping...", "stopping") 
            self.btn_stop.configure(state="disabled")

        self.lbl_stopwatch.stopAndReset()
        

        
    def update_status(self, text, state_code):
        if not self.winfo_exists(): return # [ADD THIS LINE]
        self.state = state_code
        self.lbl_status.configure(text=text)
        if state_code == "done": self.lbl_status.configure(text_color="#2ecc71")
        elif state_code == "error": self.lbl_status.configure(text_color="#e74c3c")
        elif state_code == "processing": self.lbl_status.configure(text_color="#3498db")
        else: self.lbl_status.configure(text_color="gray")

    def reset_ui(self):
        self.transcription_text = ""
        self.progress_bar.set(0)
        self.cancel_flag = False
        self.btn_copy.configure(state="disabled")
        self.btn_save.configure(state="disabled")
        

    def on_progress(self, percent, chunk_text):
        if not self.winfo_exists(): return
        self.progress_bar.set(percent)
        self.lbl_status.configure(text=f"Processing {int(percent*100)}%")
        if chunk_text:
            self.transcription_text += chunk_text + " "

    def finish_success(self):
        self.progress_bar.set(1)
        self.update_status("Completed", "done")
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="disabled")

        self.btn_view.configure(state="normal")
        self.btn_copy.configure(state="normal")
        self.btn_save.configure(state="normal")

    # [REPLACE THE EXISTING finish_stopped WITH THIS]
    def finish_stopped(self):
        if not self.winfo_exists(): return
        self.update_status("Stopped", "idle")  
        self.progress_bar.set(0)
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")

    def finish_error(self, err_msg):
        short_msg = err_msg if len(err_msg) <= 180 else err_msg[:177] + "..."
        self.update_status(f"Error: {short_msg}", "error")
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")

    def copy_text(self):
        # 1. Verify file exists
        if os.path.exists(self.recovery_file):
            try:
                # 2. Read and Copy to Clipboard
                with open(self.recovery_file, "r", encoding="utf-8") as f:
                    text = f.read()
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

            except Exception as e: 
                print(f"Copy Failed: {e}")

    def save_text(self):
        if not os.path.exists(self.recovery_file): return
        default_name = f"{os.path.splitext(self.filename)[0]}_transcript.txt"
        save_path = filedialog.asksaveasfilename(defaultextension=".txt", initialfile=default_name)
        if save_path:
            with open(self.recovery_file, "r", encoding="utf-8") as src, open(save_path, "w", encoding="utf-8") as dst:
                dst.write(src.read())
