import ctypes
import os

from ctk_ui.app import TranscriberQueueApp, log_runtime_error

# Matches AppMutex in installer\Transcriber.iss. Holding it is how a running copy tells
# the wizard to ask the user to close the app before its files are replaced.
APP_MUTEX_NAME = "TranscriberAppRunningMutex"

# Without an explicit identity Windows attributes the window to the interpreter that
# launched it, and the taskbar shows a generic Python icon instead of Transcriber's.
APP_USER_MODEL_ID = "Transcriber.App"


def claim_windows_identity():
    """Best-effort: neither failure is worth refusing to start over."""
    if os.name != "nt":
        return None

    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        pass

    try:
        # Kept alive for the process lifetime by returning it to the caller.
        return ctypes.windll.kernel32.CreateMutexW(None, False, APP_MUTEX_NAME)
    except Exception:
        return None


if __name__ == "__main__":
    mutex = claim_windows_identity()

    app = TranscriberQueueApp()
    try:
        app.mainloop()
    except BaseException as exc:
        # A crash must still end the process: the GPU driver only reclaims this app's
        # VRAM once it is really gone, and a half-dead window would keep holding it.
        log_runtime_error("Unhandled exception in mainloop", exc)
        os._exit(1)
    os._exit(0)
