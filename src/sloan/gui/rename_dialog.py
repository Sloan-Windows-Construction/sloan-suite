import os, time
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (QDialog, QLabel, QComboBox, QPushButton, QLineEdit, QCheckBox,
                             QVBoxLayout, QHBoxLayout, QGroupBox, QGridLayout, QToolButton, QMessageBox, QApplication)
from PyQt5.QtGui import QIcon, QCursor

from ..config import load_config
from ..naming import Namer
from .settings_dialog import SettingsDialog

class RenameDialog(QDialog):
    settings_saved = pyqtSignal()
    def __init__(self, file_path: str, cfg, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sloan File Renamer")
        self.setMinimumWidth(540)
        self.file_path = file_path
        self.cfg = cfg
        self.namer = Namer(cfg)

        main = QVBoxLayout(self)
        top = QHBoxLayout(); self.title_lbl = QLabel("Select details for renaming")
        self.btn_gear = QToolButton(); self.btn_gear.setText("⚙"); self.btn_gear.setToolTip("Open Settings")
        self.btn_gear.clicked.connect(self.open_settings)
        top.addWidget(self.title_lbl); top.addStretch(1); top.addWidget(self.btn_gear)
        main.addLayout(top)

        # Step 1
        step1 = QGroupBox("Step 1 — Keyword"); s1 = QGridLayout(step1)
        self.keyword_cb = QComboBox(); self.keyword_cb.addItems([k["name"] for k in self.cfg.get("keywords", [])])
        s1.addWidget(QLabel("Keyword"), 0, 0); s1.addWidget(self.keyword_cb, 0, 1)
        main.addWidget(step1)

        # Step 2 — Additional Options
        step2 = QGroupBox("Step 2 — Additional Options");
        s2 = QGridLayout(step2)

        self.lbl_brand = QLabel("Brand")
        self.brand_cb = QComboBox();
        self.brand_cb.addItems([b["name"] for b in self.cfg.get("brands", [])])

        self.lbl_side = QLabel("Side")
        self.side_cb = QComboBox();
        self.side_cb.addItems(["Interior", "Exterior"])

        self.lbl_loc = QLabel("Location")
        self.loc_cb = QComboBox()

        self.extra_tag_chk = QCheckBox("Add Extra Tag")
        self.extra_tag_edit = QLineEdit();
        self.extra_tag_edit.setPlaceholderText("Type extra tag…")

        row = 0
        s2.addWidget(self.lbl_brand, row, 0);
        s2.addWidget(self.brand_cb, row, 1);
        row += 1
        s2.addWidget(self.lbl_side, row, 0);
        s2.addWidget(self.side_cb, row, 1);
        row += 1
        s2.addWidget(self.lbl_loc, row, 0);
        s2.addWidget(self.loc_cb, row, 1);
        row += 1
        # Extra tag row (checkbox controls textbox visibility)
        s2.addWidget(self.extra_tag_chk, row, 0);
        s2.addWidget(self.extra_tag_edit, row, 1)

        # Start hidden; refresh_options_visibility() will toggle correctly
        for w in (self.lbl_brand, self.brand_cb, self.lbl_side, self.side_cb, self.lbl_loc, self.loc_cb):
            w.hide()
        self.extra_tag_edit.hide()

        main.addWidget(step2)

        self.preview_lbl = QLabel("Preview: …")
        self.rename_btn = QPushButton("Rename File"); self.rename_btn.clicked.connect(self.do_rename)
        main.addWidget(self.preview_lbl); main.addWidget(self.rename_btn)

        # Signals
        self.keyword_cb.currentTextChanged.connect(self.refresh_options_visibility)
        self.side_cb.currentTextChanged.connect(self.populate_locations)
        self.brand_cb.currentTextChanged.connect(self.update_preview)
        self.loc_cb.currentTextChanged.connect(self.update_preview)
        for w in (self.brand_cb, self.loc_cb):
            w.currentTextChanged.connect(self.update_preview)
        self.extra_tag_chk.stateChanged.connect(
            lambda _: self.extra_tag_edit.setVisible(self.extra_tag_chk.isChecked())
        )
        self.extra_tag_chk.stateChanged.connect(self.update_preview)
        self.extra_tag_edit.textChanged.connect(self.update_preview)

        self.refresh_options_visibility(); self.center_on_cursor_screen(); QTimer.singleShot(50, self.update_preview)

    def center_on_cursor_screen(self):
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.activateWindow(); self.raise_()
        screen = self.screen() or self.windowHandle().screen()
        if screen:
            geo = screen.availableGeometry()
            self.move(geo.center() - self.rect().center())

    def open_settings(self):
        dlg = SettingsDialog(load_config(), self)

        # prefer the explicit path if the app gave us one; otherwise use the app icon
        path = getattr(self, "app_icon_path", "")
        icon = QIcon(path) if path else QApplication.instance().windowIcon()
        if not icon.isNull():
            dlg.setWindowIcon(icon)

        if dlg.exec_():
            self.settings_saved.emit()
            self.cfg = load_config();
            self.namer = Namer(self.cfg)
            self.keyword_cb.blockSignals(True)
            cur_kw = self.keyword_cb.currentText()
            self.keyword_cb.clear();
            self.keyword_cb.addItems([k["name"] for k in self.cfg.get("keywords", [])])
            if cur_kw in [k["name"] for k in self.cfg.get("keywords", [])]:
                self.keyword_cb.setCurrentText(cur_kw)
            self.keyword_cb.blockSignals(False)
            self.refresh_options_visibility();
            self.update_preview()

    def _is_quote(self, kw: str) -> bool:
        return kw in ("Initial Quote", "Final Quote")

    def _is_picture(self, kw: str) -> bool:
        return kw in ("Initial Picture", "Final Picture")

    def populate_locations(self):
        side = self.side_cb.currentText() or "Interior"
        locs = self.cfg.get("locations", {}).get(side, [])
        self.loc_cb.blockSignals(True)
        self.loc_cb.clear()
        self.loc_cb.addItems([l["name"] for l in locs])
        self.loc_cb.blockSignals(False)
        self.update_preview()

    def refresh_options_visibility(self):
        kw = self.keyword_cb.currentText()
        is_quote = self._is_quote(kw)
        is_pic = self._is_picture(kw)

        # Brand shows only for quotes
        for w in (self.lbl_brand, self.brand_cb):
            w.setVisible(is_quote)

        # Side+Location show only for pictures
        for w in (self.lbl_side, self.side_cb, self.lbl_loc, self.loc_cb):
            w.setVisible(is_pic)

        # Reset irrelevant fields so they don't leak into preview
        if is_quote:
            # Clear picture selections
            self.side_cb.blockSignals(True);
            self.loc_cb.blockSignals(True)
            self.side_cb.setCurrentIndex(0)
            self.loc_cb.clear()
            self.loc_cb.blockSignals(False);
            self.side_cb.blockSignals(False)
        elif is_pic:
            # Clear brand selection; (re)populate locations for current side
            self.brand_cb.setCurrentIndex(0)
            self.populate_locations()
        else:
            # Blueprint / Completion Form / Measure Sheet, etc.
            self.brand_cb.setCurrentIndex(0)
            self.side_cb.setCurrentIndex(0)
            self.loc_cb.clear()

        # Extra tag textbox visibility follows checkbox
        self.extra_tag_edit.setVisible(self.extra_tag_chk.isChecked())

        self.update_preview()

    def parse_customer_from_original(self) -> str:
        base = os.path.splitext(os.path.basename(self.file_path))[0]
        tokens = base.split()
        if len(tokens) >= 2 and tokens[0][0:1].isupper() and tokens[1][0:1].isupper():
            return f"{tokens[0]} {tokens[1]}"
        return base

    def update_preview(self):
        kw = self.keyword_cb.currentText()
        is_quote = self._is_quote(kw)
        is_pic = self._is_picture(kw)

        ext = os.path.splitext(self.file_path)[1]
        customer = self.parse_customer_from_original()

        # Extra only if checked (and non-empty)
        extra = self.extra_tag_edit.text().strip() if self.extra_tag_chk.isChecked() else ""

        detail_full = ""
        is_brand = False

        if is_quote:
            detail_full = self.brand_cb.currentText() or ""
            is_brand = True
        elif is_pic:
            side = self.side_cb.currentText() or "Interior"
            loc = self.loc_cb.currentText() or ""
            # Use acronym for locations (per original spec)
            detail_full = self.namer.location_acronym(side, loc) if loc else ""

        name, _ = self.namer.render(customer, kw, detail_full, is_brand, None, ext, extra=extra)
        self.preview_lbl.setText(f"Preview: {name}")

    def do_rename(self):
        try:
            kw = self.keyword_cb.currentText()
            is_quote = self._is_quote(kw);
            is_pic = self._is_picture(kw)
            ext = os.path.splitext(self.file_path)[1]
            customer = self.parse_customer_from_original()
            extra = self.extra_tag_edit.text().strip() if self.extra_tag_chk.isChecked() else ""
            detail_full = "";
            is_brand = False
            if is_quote:
                detail_full = self.brand_cb.currentText() or "";
                is_brand = True
            elif is_pic:
                side = self.side_cb.currentText() or "Interior";
                loc = self.loc_cb.currentText() or ""
                detail_full = self.namer.location_acronym(side, loc)

            new_name, _ = self.namer.render(customer, kw, detail_full, is_brand, None, ext, extra=extra)
            folder = os.path.dirname(self.file_path);
            new_path = os.path.join(folder, new_name)


            # --- BEGIN: suppress watcher during our own rename
            lock_path = os.path.join(folder, ".sloan_renaming")
            try:
                with open(lock_path, "w", encoding="utf-8") as _f:
                    _f.write("1")
            except Exception:
                pass
            self.repaint();  # ensure UI stays responsive
            # --- END: create lock

            if os.path.abspath(self.file_path) != os.path.abspath(new_path):
                if os.path.exists(new_path):
                    stem, e = os.path.splitext(new_path); i = 2
                    while os.path.exists(f"{stem} ({i}){e}"):
                        i += 1
                    new_path = f"{stem} ({i}){e}"
                os.rename(self.file_path, new_path)
                self.file_path = new_path

            # small delay to let filesystem settle before we drop the lock
            time.sleep(0.2)

        finally:
            # --- BEGIN: always remove lock
            try:
                if os.path.exists(lock_path):
                    os.remove(lock_path)
            except Exception:
                pass
            # --- END: remove lock

        self.accept()