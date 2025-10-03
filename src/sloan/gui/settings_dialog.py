import json

from PyQt5.QtWidgets import (QDialog, QWidget, QGridLayout, QLineEdit, QPushButton, QLabel,
                             QPlainTextEdit, QTabWidget, QHBoxLayout, QVBoxLayout, QFileDialog, QMessageBox)
from ..config import load_config, save_config, DEFAULT_CONFIG, DATE_FMT_DEFAULT

class SettingsDialog(QDialog):
    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sloan Settings")
        self.setMinimumSize(720, 520)
        self.cfg = dict(cfg)
        self.tabs = QTabWidget()

        # Common

        common = QWidget(); grid = QGridLayout(common)
        self.watch_edit = QLineEdit(self.cfg.get("watch_folder", ""))
        btn_browse = QPushButton("Browse…"); btn_browse.clicked.connect(self.browse_watch)
        self.template_edit = QLineEdit(self.cfg.get("filename_template", DEFAULT_CONFIG["filename_template"]))
        self.datefmt_edit = QLineEdit(self.cfg.get("date_format", DATE_FMT_DEFAULT))
        grid.addWidget(QLabel("Watch Folder"), 0, 0); grid.addWidget(self.watch_edit, 0, 1); grid.addWidget(btn_browse, 0, 2)
        grid.addWidget(QLabel("Filename Template"), 1, 0); grid.addWidget(self.template_edit, 1, 1, 1, 2)
        grid.addWidget(QLabel("Date Format (strftime)"), 2, 0); grid.addWidget(self.datefmt_edit, 2, 1, 1, 2)

        # Rename Config
        rename_tab = QWidget(); rgrid = QGridLayout(rename_tab)
        self.keywords_edit = QPlainTextEdit(self._list_to_lines(self.cfg.get("keywords", [])))
        self.brands_edit = QPlainTextEdit(self._list_to_lines(self.cfg.get("brands", [])))
        locs = self.cfg.get("locations", {})
        self.interior_edit = QPlainTextEdit(self._list_to_lines(locs.get("Interior", [])))
        self.exterior_edit = QPlainTextEdit(self._list_to_lines(locs.get("Exterior", [])))
        rgrid.addWidget(QLabel("Keywords (Name | Acronym)"), 0, 0); rgrid.addWidget(self.keywords_edit, 1, 0)
        rgrid.addWidget(QLabel("Brands (Name | Acronym)"), 0, 1); rgrid.addWidget(self.brands_edit, 1, 1)
        rgrid.addWidget(QLabel("Interior Locations (Name | Acronym)"), 2, 0); rgrid.addWidget(self.interior_edit, 3, 0)
        rgrid.addWidget(QLabel("Exterior Locations (Name | Acronym)"), 2, 1); rgrid.addWidget(self.exterior_edit, 3, 1)

        # Organizer Config
        org_tab = QWidget(); ogrid = QGridLayout(org_tab)
        org = self.cfg.get("organizer", {})
        self.customer_root_edit = QLineEdit(org.get("customer_root_path", "/Customers"))
        self.downloads_path_edit = QLineEdit(org.get("downloads_folder_path", "/Downloads"))
        self.default_tree_edit = QPlainTextEdit("\n".join(org.get("create_default_tree", [])))
        self.routing_edit = QPlainTextEdit("\n".join([f"{k} -> {v}" for k, v in org.get("routing", {}).items()]))
        ogrid.addWidget(QLabel("Customer Root Path"), 0, 0); ogrid.addWidget(self.customer_root_edit, 0, 1)
        ogrid.addWidget(QLabel("Downloads Folder Path"), 1, 0); ogrid.addWidget(self.downloads_path_edit, 1, 1)
        ogrid.addWidget(QLabel("Default Folder Tree (one per line)"), 2, 0); ogrid.addWidget(self.default_tree_edit, 3, 0, 1, 2)
        ogrid.addWidget(QLabel("Keyword Routing (InitialP -> /Initial/Pictures)"), 4, 0); ogrid.addWidget(self.routing_edit, 5, 0, 1, 2)

        self.tabs.addTab(common, "Common")
        self.tabs.addTab(rename_tab, "Rename Config")
        self.tabs.addTab(org_tab, "Organizer Config")


        btns = QHBoxLayout(); save_btn = QPushButton("Save"); cancel_btn = QPushButton("Cancel")
        save_btn.clicked.connect(self.on_save); cancel_btn.clicked.connect(self.reject)
        btns.addStretch(1); btns.addWidget(save_btn); btns.addWidget(cancel_btn)

        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.clicked.connect(self.on_reset_defaults)
        btns.addWidget(reset_btn)

        layout = QVBoxLayout(self); layout.addWidget(self.tabs); layout.addLayout(btns)

    def browse_watch(self):
        d = QFileDialog.getExistingDirectory(self, "Select Watch Folder", self.watch_edit.text())
        if d: self.watch_edit.setText(d)

    @staticmethod
    def _list_to_lines(items):
        return "\n".join([f"{it.get('name','')} | {it.get('acronym','')}" for it in items])

    @staticmethod
    def _lines_to_list(txt):
        out = []
        for line in txt.splitlines():
            line = line.strip()
            if not line: continue
            if "|" in line:
                name, acr = [p.strip() for p in line.split("|", 1)]
            else:
                name, acr = line, line
            out.append({"name": name, "acronym": acr})
        return out

    def on_save(self):
        try:
            # 1) Collect fields
            self.cfg["watch_folder"] = self.watch_edit.text().strip()
            self.cfg["filename_template"] = self.template_edit.text().strip()
            self.cfg["date_format"] = self.datefmt_edit.text().strip() or DATE_FMT_DEFAULT
            self.cfg["keywords"] = self._lines_to_list(self.keywords_edit.toPlainText())
            self.cfg["brands"] = self._lines_to_list(self.brands_edit.toPlainText())
            self.cfg.setdefault("locations", {})["Interior"] = self._lines_to_list(self.interior_edit.toPlainText())
            self.cfg.setdefault("locations", {})["Exterior"] = self._lines_to_list(self.exterior_edit.toPlainText())
            org = self.cfg.setdefault("organizer", {})
            org["customer_root_path"] = self.customer_root_edit.text().strip() or "/Customers"
            org["downloads_folder_path"] = self.downloads_path_edit.text().strip() or "/Downloads"
            org["create_default_tree"] = [ln.strip() for ln in self.default_tree_edit.toPlainText().splitlines() if
                                          ln.strip()]
            routing = {}
            for ln in self.routing_edit.toPlainText().splitlines():
                if "->" in ln:
                    k, v = [p.strip() for p in ln.split("->", 1)]
                    routing[k] = v
            org["routing"] = routing

            # 2) Minimal template validation (warn, don’t block)
            tmpl = self.cfg["filename_template"]
            if "{" in tmpl and "}" in tmpl:
                # Known placeholders we support:
                allowed = {"customer", "keyword", "detail", "date", "extra"}
                import re
                bad = [m for m in re.findall(r"{([^{}]+)}", tmpl) if m not in allowed]
                if bad:
                    QMessageBox.warning(self, "Template Warning",
                                        f"Unknown placeholders in template will be empty: {', '.join(bad)}")

            # 3) Save to disk
            save_config(self.cfg)

            # 4) Read back and verify it stuck
            after = load_config()
            if after.get("filename_template") != self.cfg.get("filename_template"):
                QMessageBox.critical(self, "Save Failed",
                                     "The file name template did not persist to disk. "
                                     "Please check permissions for your user profile folder.")
                return

            QMessageBox.information(self, "Saved", "Settings saved successfully.")
            self.accept()
        except Exception as ex:
            QMessageBox.critical(self, "Save Error", str(ex))

    def on_reset_defaults(self):
        from ..config import DEFAULT_CONFIG, save_config, load_config
        # Keep sensitive/tenant fields if you want:
        preserved = self.cfg.get("graph", {})
        new_cfg = json.loads(json.dumps(DEFAULT_CONFIG))
        new_cfg["graph"] = preserved  # optional: keep creds
        save_config(new_cfg)
        QMessageBox.information(self, "Reset", "Config reset to defaults.")
        self.cfg = load_config()
        # refresh UI fields from self.cfg here...
