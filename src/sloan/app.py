import os, sys, time, threading, traceback

from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QObject
from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox

from .config import load_config
from .tray import Tray
from .gui.rename_dialog import RenameDialog
from .gui.settings_dialog import SettingsDialog
from .services.graph_client import GraphClient
from .services.organizer import Organizer
from .services.jotform_poller import JotformPoller
from watchdog.observers import Observer
from .utils.log import log
from .watcher import CreatedModifiedHandler
import argparse
import ctypes, os
from PyQt5.QtGui import QIcon
from .utils.resource_path import resource_path

print("[SLOAN] app.py loaded"); log("app.py loaded")


class Controller(QObject):
    file_detected = pyqtSignal(str)
    open_config = pyqtSignal()

class SloanApp:
    def __init__(self):
        self.cfg = load_config()
        self.started_at = time.time()
        self.seen_paths = set()  # files we’ve already handled
        self.baseline = set()
        watch = self.cfg.get("watch_folder")
        if os.path.isdir(watch):
            # Snapshot existing files at startup so we ignore them
            self.baseline = {os.path.abspath(os.path.join(watch, n))
                             for n in os.listdir(watch)
                             if os.path.isfile(os.path.join(watch, n))}

        self.controller = Controller()
        self.app = QApplication(sys.argv)
        # (Windows) set an explicit AppUserModelID so taskbar/pin uses our icon
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SloanSuite.Sloan")  # any stable string
        except Exception:
            pass

        # Set application icon (used for taskbar if there’s a top-level window)
        icon_path = resource_path("assets/icon.ico")
        self.app.setWindowIcon(QIcon(icon_path))
        self.app_icon_path = icon_path  # stash for dialogs/tray

        self.app.setQuitOnLastWindowClosed(False)
        self.tray = Tray(self.app, self.controller)
        self.graph = GraphClient(self.cfg)
        self.organizer = Organizer(self.cfg, self.graph)
        self.stop_evt = threading.Event()

        # Jotform thread
        self.jf_stop = threading.Event()
        self.jf_thread = JotformPoller(self.cfg, self.graph, self.jf_stop, log_fn=lambda m: print(m))
        self.jf_thread.start()

        # Watcher
        self.observer = Observer()
        q = float(self.cfg.get("watch", {}).get("quiet_seconds", 1.5))
        handler = CreatedModifiedHandler(self.on_file_ready, quiet_seconds=q)
        watch = self.cfg.get("watch_folder")
        log(f"Starting Qt loop. Watching: {watch}")
        os.makedirs(watch, exist_ok=True)
        self.observer.schedule(handler, watch, recursive=False)
        self.observer.start()

        # Signals
        self.controller.file_detected.connect(self.show_rename_dialog)
        self.controller.open_config.connect(self.show_settings)

        self.sweep_timer = QTimer(); self.sweep_timer.timeout.connect(self.sweep_watch_folder)
        self.sweep_timer.start(60000)

    def show_settings(self):
        dlg = SettingsDialog(load_config())
        # set settings window icon
        icon = QIcon(self.app_icon_path) if getattr(self, "app_icon_path", "") else QApplication.instance().windowIcon()
        if not icon.isNull():
            dlg.setWindowIcon(icon)

        if dlg.exec_() == QDialog.Accepted:
            self.cfg = load_config()
            try:
                self.observer.stop();
                self.observer.join(2)
            except Exception:
                pass
            self.observer = Observer()
            self.observer.schedule(CreatedModifiedHandler(self.on_file_ready), self.cfg.get("watch_folder"),
                                   recursive=False)
            self.observer.start()

    def show_rename_dialog(self, file_path: str):
        print(f"[SLOAN] show_rename_dialog({file_path})")
        try:
            dlg = RenameDialog(file_path, load_config())

            # set rename window icon
            icon = QIcon(self.app_icon_path) if getattr(self, "app_icon_path",
                                                        "") else QApplication.instance().windowIcon()
            if not icon.isNull():
                dlg.setWindowIcon(icon)

            dlg.show()  # ensure visible
            if dlg.exec_() == QDialog.Accepted:
                renamed = dlg.file_path
                self.seen_paths.add(os.path.abspath(renamed))
                customer = dlg.parse_customer_from_original()
                from .naming import Namer
                kw_text = dlg.keyword_cb.currentText()
                kw_acr = Namer(load_config()).keyword_acronym(kw_text)
                dl = self.cfg.get("organizer", {}).get("downloads_folder_path", "/Downloads")
                up = self.graph.upload_small(f"{dl}/{os.path.basename(renamed)}", renamed)
                self.organizer.move_uploaded_to_customer(up, customer, kw_acr)
        except Exception as ex:
            QMessageBox.critical(None, "Error", str(ex))

    def _on_settings_saved(self):
        self.cfg = load_config()
        try:
            self.observer.stop();
            self.observer.join(2)
        except Exception:
            pass
        self.observer = Observer()
        self.observer.schedule(CreatedModifiedHandler(self.on_file_ready), self.cfg.get("watch_folder"),
                               recursive=False)
        self.observer.start()

    def on_file_ready(self, path: str):
        print(f"[SLOAN] on_file_ready received: {path}")
        if self._should_process(path):
            self.seen_paths.add(os.path.abspath(path))
            self.controller.file_detected.emit(path)
            print("[SLOAN] Emitting file_detected")


    def sweep_watch_folder(self):
        try:
            watch_cfg = self.cfg.get("watch", {})
            if not watch_cfg.get("sweep_enabled", False):
                return
            folder = self.cfg.get("watch_folder")
            max_age = int(watch_cfg.get("sweep_age_seconds", 120))
            now = time.time()
            for name in os.listdir(folder):
                p = os.path.join(folder, name)
                if not os.path.isfile(p):
                    continue
                ext = os.path.splitext(p)[1].lower()
                if ext in {".crdownload", ".opdownload", ".tmp", ".part"}:
                    continue
                try:
                    mtime = os.path.getmtime(p)
                except Exception:
                    continue
                # Only sweep files that are stable AND created/modified after app start
                if (now - mtime) > max_age and mtime >= self.started_at and self._should_process(p):
                    self.seen_paths.add(os.path.abspath(p))
                    self.controller.file_detected.emit(p)
        except Exception:
            pass

    def run(self):
        parser = argparse.ArgumentParser(add_help=False)
        parser.add_argument("--open", dest="open_path", help="Open Rename dialog for this file path")
        args, _ = parser.parse_known_args()

        watch = self.cfg.get("watch_folder")
        print(f"[SLOAN] Starting Qt loop. Watching: {watch}")

        if args.open_path:
            path = os.path.abspath(args.open_path)
            print(f"[SLOAN] --open requested: {path}")
            if os.path.exists(path):
                QTimer.singleShot(0, lambda: self.show_rename_dialog(path))
            else:
                print(f"[SLOAN] --open path NOT FOUND: {path}")

        sys.exit(self.app.exec_())

    def shutdown(self):
        self.stop_evt.set()
        try:
            self.observer.stop(); self.observer.join(2)
            self.jf_stop.set()
            self.jf_thread.join(timeout=5)
        except Exception:
            pass

    def _should_process(self, path: str) -> bool:
        path = os.path.abspath(path)
        # Ignore files that existed when the app started (baseline)
        if not self.cfg.get("watch", {}).get("process_existing_on_start", False):
            if path in self.baseline:
                return False
        # Don't re-process the same path in this session
        if path in self.seen_paths:
            return False
        return True


def main():
    app = SloanApp()
    try:
        app.run()
    finally:
        app.shutdown()


if __name__ == "__main__":
    main()
