import os

from ctk_ui.app import TranscriberQueueApp, log_runtime_error

if __name__ == "__main__":
    app = TranscriberQueueApp()
    try:
        app.mainloop()
    except BaseException as exc:
        # A crash must still end the process: the GPU driver only reclaims this app's
        # VRAM once it is really gone, and a half-dead window would keep holding it.
        log_runtime_error("Unhandled exception in mainloop", exc)
        os._exit(1)
    os._exit(0)
