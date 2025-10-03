import sys, os
from PyQt5.QtWidgets import QMessageBox

def register_context_menu():
    try:
        import winreg
        if getattr(sys, 'frozen', False):
            exe = sys.executable; cmd = f'"{exe}" "%1"'
        else:
            script = os.path.abspath(__file__)  # will be overridden by entrypoint handling
            cmd = f'"{sys.executable}" -m sloan.app --open "%1"'
        key_path = r"*\\shell\\Edit with Sloan"
        with winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, key_path) as k:
            winreg.SetValueEx(k, None, 0, winreg.REG_SZ, "Edit with Sloan")
        with winreg.CreateKey(winreg.HKEY_CLASSES_ROOT, key_path + r"\command") as c:
            winreg.SetValueEx(c, None, 0, winreg.REG_SZ, cmd)
        QMessageBox.information(None, "Context Menu", "Registered 'Edit with Sloan'.")
    except Exception as ex:
        QMessageBox.critical(None, "Context Menu", f"Failed to register: {ex}")