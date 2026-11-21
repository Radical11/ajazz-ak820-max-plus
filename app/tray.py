"""
tray.py - System-tray icon: open the window, switch profiles, lighting off, quit.
No-ops gracefully if pystray is unavailable.
"""

from __future__ import annotations

import logging
import threading

log = logging.getLogger(__name__)

try:
    import pystray
    from PIL import Image, ImageDraw
    PYSTRAY_AVAILABLE = True
except ImportError:
    PYSTRAY_AVAILABLE = False


def _make_icon_image(size: int = 64):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([(2, 12), (size - 2, size - 12)], radius=9, fill=(24, 24, 27))
    colors = [(244, 63, 94), (168, 85, 247), (56, 189, 248)]
    for i, c in enumerate(colors):
        x = 10 + i * 16
        d.rounded_rectangle([(x, 22), (x + 12, 42)], radius=3, fill=c)
    return img


class TrayIcon:
    def __init__(self, window, api):
        self._window = window
        self._api = api
        self._icon = None
        self.on_quit = None
        self.on_show = None
        self.running = False

    def start(self):
        if not PYSTRAY_AVAILABLE:
            return
        try:
            self._icon = pystray.Icon("ak820studio", _make_icon_image(), "AK820 Studio", self._menu())
            threading.Thread(target=self._run, daemon=True, name="Tray").start()
        except Exception as e:
            log.info("Tray unavailable: %s", e)

    def _run(self):
        self.running = True
        try:
            self._icon.run()
        except Exception as e:
            log.info("Tray stopped: %s", e)
        self.running = False

    def _menu(self):
        def show(icon=None, item=None):
            if self.on_show:
                return self.on_show()
            try:
                self._window.show()
                self._window.restore()
            except Exception:
                pass

        def profile_items():
            store = self._api._store
            active = store.settings.get("active_profile")
            for p in store.list_profiles():
                yield pystray.MenuItem(
                    p["name"],
                    (lambda pid: lambda icon, item: self._api.activate_profile(pid))(p["id"]),
                    checked=(lambda pid: lambda item: self._api._store.settings.get("active_profile") == pid)(p["id"]),
                    radio=True,
                )

        def quit_(icon, item):
            icon.stop()
            if self.on_quit:
                self.on_quit()

        return pystray.Menu(
            pystray.MenuItem("Open AK820 Studio", show, default=True),
            pystray.MenuItem("Profile", pystray.Menu(lambda: profile_items())),
            pystray.MenuItem("Lights off", lambda icon, item: self._api.turn_off()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", quit_),
        )

    def stop(self):
        if self._icon:
            try:
                self._icon.stop()
            except Exception:
                pass
