#!/usr/bin/env python3
"""
main.py - AK820 Studio entry point.

Opens the Svelte UI in the system web view (Edge WebView2 on Windows — no Qt),
runs a tray icon, and keeps working in the background when the window is closed.
  --minimized   start hidden in the tray
  --debug       enable the web inspector
"""

import logging
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
INDEX_HTML = os.path.join(ROOT, "ui", "dist", "index.html")

logging.basicConfig(level=logging.INFO if "--debug" in sys.argv else logging.WARNING,
                    format="%(asctime)s %(name)s: %(message)s")

if not os.path.isfile(INDEX_HTML):
    print("[ERROR] Frontend not built. Run:  cd ui && npm install && npm run build", file=sys.stderr)
    sys.exit(1)


def _single_instance() -> bool:
    """Return False if another AK820 Studio is already running (Windows)."""
    if os.name != "nt":
        return True
    import ctypes
    ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\AK820Studio")
    return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


def main():
    if not _single_instance():
        print("AK820 Studio is already running (check the tray).")
        return

    import webview
    from app.api import KeyboardAPI
    from app.tray import TrayIcon

    api = KeyboardAPI()
    minimized = "--minimized" in sys.argv or api._store.settings.get("start_minimized")

    window = webview.create_window(
        title="AK820 Studio",
        url=INDEX_HTML,
        js_api=api,
        width=1180,
        height=760,
        min_size=(980, 640),
        background_color="#09090b",
        hidden=bool(minimized),
    )
    api._attach(window)
    tray = TrayIcon(window, api)
    state = {"quitting": False}

    def on_closing():
        if api._store.settings.get("close_to_tray", True) and tray.running and not state["quitting"]:
            window.hide()
            return False  # keep running in the tray
        api._shutdown()
        tray.stop()
        return True

    def quit_app():
        state["quitting"] = True
        window.destroy()

    tray.on_quit = quit_app
    window.events.closing += on_closing

    def started():
        tray.start()
        api._start_background()

    webview.start(started, debug="--debug" in sys.argv, private_mode=False,
                  storage_path=os.path.join(os.environ.get("APPDATA", ROOT), "AK820Studio", "webview"))


if __name__ == "__main__":
    main()
