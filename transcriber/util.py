from mutagen.mp3 import MP3
from mutagen.wave import WAVE
import os
import shutil
import time
import stat
import sys


class Util():
    @staticmethod
    def get_audio_duration(file_path):
        """
        Returns the duration of the audio file in seconds (float).
        Returns 0 if it fails or format is unsupported.
        """
        if not os.path.exists(file_path):
            return 0

        try:
            # Check file extension
            ext = os.path.splitext(file_path)[1].lower()

            if ext == '.mp3':
                audio = MP3(file_path)
                return audio.info.length  # Duration in seconds
            
            elif ext == '.wav':
                audio = WAVE(file_path)
                return audio.info.length
                
            else:
                # Fallback for other formats (requires 'mutagen.File')
                from mutagen import File
                audio = File(file_path)
                if audio is not None and audio.info is not None:
                    return audio.info.length
                
        except Exception as e:
            print(f"Error reading duration: {e}")
        
        return 0

    # --- Helper to make it readable (MM:SS) ---
    @staticmethod
    def format_duration(seconds):
        if not seconds: return "00:00"
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        
        if h > 0:
            return f"{h:d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"
    

 
    @staticmethod
    def resource_path(relative_path):
        """ Get absolute path to resource, works for dev and for PyInstaller """
        try:
            # PyInstaller creates a temp folder and stores path in _MEIPASS
            base_path = sys._MEIPASS
        except Exception:
            # If not running as an exe, use the current script directory
            base_path = os.path.abspath(".")

        return os.path.join(base_path, relative_path)
    @staticmethod
    def force_delete_folder(folder_path, max_retries=10, delay=0.1):
        """
        Safely deletes a folder and all its contents, with retry logic for locked files.
        
        Args:
            folder_path (str): Path to the folder to delete.
            max_retries (int): How many times to try before giving up.
            delay (float): Seconds to wait between retries.
        """
        
        # 1. Helper to force-delete read-only files (common Windows issue)
        def on_rm_error(func, path, exc_info):
            # Check if the file is read-only
            if not os.access(path, os.W_OK):
                # Change permissions to "Write"
                os.chmod(path, stat.S_IWRITE)
                # Retry the function (os.unlink or os.rmdir)
                func(path)
            else:
                # If it's not a permission issue, raise the error (to trigger retry loop)
                raise

        # 2. Check if folder exists first
        if not os.path.exists(folder_path):
            return True

        # 3. Retry Loop
        for attempt in range(max_retries):
            try:
                # The magic command: tries to delete everything
                # onerror=on_rm_error handles the "Access Denied" for read-only files
                shutil.rmtree(folder_path, onerror=on_rm_error)
                
                print(f"Successfully deleted: {folder_path}")
                return True # Success!

            except OSError as e:
                # Check if this is the last attempt
                if attempt == max_retries - 1:
                    print(f"Failed to delete {folder_path} after {max_retries} attempts. Error: {e}")
                    return False
                
                # Wait a tiny bit for the OS to release file locks
                time.sleep(delay)
                
        return False
