import customtkinter as ctk

class StopWatchLabel(ctk.CTkLabel):
    def __init__(self, master, **kwargs):
        # Set default text if the user didn't provide one
        if "text" not in kwargs:
            kwargs["text"] = "00:00"
            
        # Initialize the Label (pass all styling options to the parent)
        super().__init__(master, **kwargs)
        
        # Internal state variables
        self.seconds = 0
        self.running = False


    def start(self):
        if not self.running:
            self.running = True
            self.update_timer()

    def stop(self):
        self.running = False
        
    def stopAndReset(self):
        self.stop()
        self.reset()


    def reset(self):
        self.seconds = 0
        self.configure(text="00:00")

    def update_timer(self):
        # 1. Check if we should keep running
        # 2. Check if the label still exists (prevents crash if window closes)
        if self.running and self.winfo_exists():
            self.seconds += 1
            
            # Math: Convert total seconds to M:S
            minutes, secs = divmod(self.seconds, 60)
            
            
            # Update the text of THIS label
            self.configure(text=f"{minutes:02d}:{secs:02d}")
            
            # Schedule the next update in 1000ms (1 second)
            self.after(1000, self.update_timer)