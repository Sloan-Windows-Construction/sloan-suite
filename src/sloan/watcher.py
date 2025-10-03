# src/sloan/watcher.py
import os, time, threading
from watchdog.events import FileSystemEventHandler

# Common temp/incomplete patterns
TEMP_EXT = {".crdownload", ".opdownload", ".part", ".tmp"}
TEMP_PREFIXES = {"~$"}  # Office temp files
LOCKFILE_NAME = ".sloan_renaming"

def _renaming_lock_present(path: str) -> bool:
    # ignore events while we are renaming (lock file lives in the watched folder)
    folder = os.path.dirname(path)
    return os.path.exists(os.path.join(folder, LOCKFILE_NAME))

def _looks_temp(path: str) -> bool:
    name = os.path.basename(path).lower()
    ext = os.path.splitext(name)[1]
    if ext in TEMP_EXT:
        return True
    return any(name.startswith(pfx) for pfx in TEMP_PREFIXES)

def _is_file_stable(path: str, quiet_seconds: float = 1.5, checks: int = 6, delay: float = 0.4) -> bool:
    """
    A file is 'stable' if:
      - it exists,
      - it's NOT a temp extension,
      - its size hasn't changed for at least `quiet_seconds`,
      - and we can open it for reading without error.
    We sample size `checks` times every `delay` seconds, requiring a continuous quiet period.
    """
    if not os.path.isfile(path) or _looks_temp(path):
        return False

    last_size = -1
    quiet_start = None
    for _ in range(checks):
        try:
            size = os.path.getsize(path)
        except OSError:
            return False

        if size != last_size:
            last_size = size
            quiet_start = time.time()
        else:
            if quiet_start and (time.time() - quiet_start) >= quiet_seconds:
                # try opening to ensure no exclusive lock
                try:
                    with open(path, "rb"):
                        return True
                except OSError:
                    return False
        time.sleep(delay)
    return False

class CreatedModifiedHandler(FileSystemEventHandler):
    """
    Debounced handler:
      - reacts to create/modify/move,
      - waits until the file is stable,
      - then calls on_file_ready(path) exactly once.
    """
    def __init__(self, on_file_ready, quiet_seconds: float = 1.5):
        super().__init__()
        self.on_file_ready = on_file_ready
        self.quiet_seconds = quiet_seconds
        self._inflight = {}  # path -> threading.Event to cancel

    def _schedule_check(self, path: str):
        if not path or not os.path.isfile(path):
            return

        # Cancel any pending checker for this path
        ev = self._inflight.pop(path, None)
        if ev:
            ev.set()

        cancel = threading.Event()
        self._inflight[path] = cancel

        def worker():
            # Skip while our own rename is in progress
            if _renaming_lock_present(path):
                return
            if _looks_temp(path):
                return
            if _is_file_stable(path, quiet_seconds=self.quiet_seconds):
                if not cancel.is_set() and self.on_file_ready:
                    self.on_file_ready(path)
            self._inflight.pop(path, None)

        threading.Thread(target=worker, daemon=True).start()

    # New files or files moved into the folder
    def on_created(self, event):
        if event.is_directory:
            return
        self._schedule_check(event.src_path)

    # Downloads often end with a rename: *.crdownload -> final.ext
    def on_moved(self, event):
        if event.is_directory:
            return
        # Final name is event.dest_path
        self._schedule_check(event.dest_path)

    # Some tools stream-write and only emit modify
    def on_modified(self, event):
        if event.is_directory:
            return
        self._schedule_check(event.src_path)


