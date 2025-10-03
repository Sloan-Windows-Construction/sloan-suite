from datetime import datetime
import os
import pathlib


APP_DIR = os.path.join(pathlib.Path.home(), ".sloan_suite")
LOG_PATH = os.path.join(APP_DIR, "sloan.log")


os.makedirs(APP_DIR, exist_ok=True)


def log(message: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {message}\n")