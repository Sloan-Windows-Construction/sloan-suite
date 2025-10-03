import os, sys


def resource_path(rel: str) -> str:
    if hasattr(sys, "_MEIPASS"):
        return os.path.join(sys._MEIPASS, rel) # type: ignore[attr-defined]
    return os.path.join(os.path.dirname(__file__), "..", rel)