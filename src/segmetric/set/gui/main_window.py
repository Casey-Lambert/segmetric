import os

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from segmetric.errors import SegMetricError
from segmetric.tag.core.discovery import find_input_files

from ..core.model import Preset
from ..core.presets import apply_preset, load_preset, save_preset
from ..core.splitting import split_filename_to_segments

LOCKED_ROW_BG = QColor(235, 235, 235)
LOCKED_ROW_FG = QColor(30, 30, 30)
COLUMN_HEADERS = ["Value", "Column header", "Select", "Object ID"]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SegMetric.Set — Preset Builder")
        self.resize(900, 640)

        self.input_folder = None
        self.sample_file = None
        self.segments = []  # list[Segment], live-edited
        self.object_id_row_index = None  # Segment.index of the flagged row, or None
        self._object_id_radios = {}  # {Segment.index: QRadioButton}, for manual exclusivity

        self._build_ui()
        self._update_button_states()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        central = QWidget()
        layout = QVBoxLayout(central)

        # -- sample file --
        sample_group = QGroupBox("Sample file")
        sample_layout = QVBoxLayout(sample_group)

        mode_row = QHBoxLayout()
        self.browse_mode_radio = QRadioButton("Upload")
        self.browse_mode_radio.setChecked(True)
        self.manual_mode_radio = QRadioButton("Manual")
        mode_group = QButtonGroup(sample_group)
        mode_group.addButton(self.browse_mode_radio)
        mode_group.addButton(self.manual_mode_radio)
        self.browse_mode_radio.toggled.connect(self.on_sample_mode_changed)
        mode_row.addWidget(self.browse_mode_radio)
        mode_row.addWidget(self.manual_mode_radio)
        mode_row.addStretch(1)
        sample_layout.addLayout(mode_row)

        self.browse_form = QWidget()
        browse_form_layout = QFormLayout(self.browse_form)
        browse_form_layout.setContentsMargins(0, 0, 0, 0)

        self.input_line = QLineEdit()
        self.input_line.setReadOnly(True)
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self.on_browse_input)
        input_row = QHBoxLayout()
        input_row.addWidget(self.input_line)
        input_row.addWidget(browse_btn)
        browse_form_layout.addRow("Input folder:", input_row)

        browse_hint = QLabel('SegMetric uses "_" to define columns.')
        browse_hint.setStyleSheet("color: gray;")
        browse_hint.setWordWrap(True)
        browse_form_layout.addRow("", browse_hint)

        sample_layout.addWidget(self.browse_form)

        self.manual_form = QWidget()
        self.manual_form.setVisible(False)
        manual_form_layout = QFormLayout(self.manual_form)
        manual_form_layout.setContentsMargins(0, 0, 0, 0)

        self.manual_name_edit = QLineEdit()
        self.manual_name_edit.setPlaceholderText("e.g. H6_120HR_34C_NR_1004_RH")
        self.manual_name_edit.editingFinished.connect(self.on_manual_filename_changed)
        manual_form_layout.addRow("Sample filename:", self.manual_name_edit)

        manual_hint = QLabel(
            "Enter file name to define format, then press <i>Enter/Return</i><br>"
            'SegMetric uses "_" to define columns.'
        )
        manual_hint.setStyleSheet("color: gray;")
        manual_hint.setWordWrap(True)
        manual_form_layout.addRow("", manual_hint)

        sample_layout.addWidget(self.manual_form)

        layout.addWidget(sample_group)

        # -- preset name --
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Preset name:"))
        self.preset_name_edit = QLineEdit()
        preset_row.addWidget(self.preset_name_edit)
        layout.addLayout(preset_row)

        # -- table --
        self.table = QTableWidget(0, len(COLUMN_HEADERS))
        self.table.setHorizontalHeaderLabels(COLUMN_HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table, stretch=1)

        table_hint = QLabel(
            "The <i>Object ID</i> is a tag used to sort files and "
            "automatically apply ID-specific settings."
        )
        table_hint.setStyleSheet("color: gray;")
        table_hint.setWordWrap(True)
        layout.addWidget(table_hint)

        # -- save / load --
        button_row = QHBoxLayout()
        self.save_btn = QPushButton("Save Preset")
        self.save_btn.clicked.connect(self.on_save_preset)
        self.load_btn = QPushButton("Load Preset")
        self.load_btn.clicked.connect(self.on_load_preset)
        button_row.addWidget(self.save_btn)
        button_row.addWidget(self.load_btn)
        layout.addLayout(button_row)

        layout.addWidget(QLabel("Status:"))
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(120)
        layout.addWidget(self.log_view)

        self.setCentralWidget(central)

    @staticmethod
    def _centered(widget):
        container = QWidget()
        wrap_layout = QHBoxLayout(container)
        wrap_layout.addWidget(widget)
        wrap_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wrap_layout.setContentsMargins(0, 0, 0, 0)
        return container

    @staticmethod
    def _locked_item(text):
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        item.setBackground(LOCKED_ROW_BG)
        item.setForeground(LOCKED_ROW_FG)
        return item

    @staticmethod
    def _readonly_item(text):
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

    # ------------------------------------------------------------- logging
    def _log(self, message):
        self.log_view.appendPlainText(message)

    def _show_error(self, message):
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle("SegMetric.Set — Error")
        box.setText(message)
        box.exec()

    # -------------------------------------------------------------- state
    def _update_button_states(self):
        ready = bool(self.segments)
        self.save_btn.setEnabled(ready)
        self.load_btn.setEnabled(ready)

    # -------------------------------------------------------- sample mode
    def on_sample_mode_changed(self, _checked):
        manual = self.manual_mode_radio.isChecked()
        self.browse_form.setVisible(not manual)
        self.manual_form.setVisible(manual)

    def _set_segments_from_text(self, name, source_label):
        """Shared by on_browse_input and on_manual_filename_changed: split
        name (a filename or filename stem, real or manually typed) into
        the segments table. source_label is what's shown/logged as the
        sample -- a real path for browse mode, the typed text itself for
        manual mode.
        """
        self.sample_file = name
        self.segments = split_filename_to_segments(name)
        self.object_id_row_index = None
        self._rebuild_table()
        self._update_button_states()
        self._log(f"Sample: {source_label}")

    # -------------------------------------------------------------- table
    def _rebuild_table(self):
        self.table.setRowCount(1 + len(self.segments))
        self._object_id_radios = {}

        sample_name = os.path.basename(self.sample_file) if self.sample_file else ""
        self.table.setItem(0, 0, self._locked_item(sample_name))
        self.table.setItem(0, 1, self._locked_item("File Name"))

        locked_checkbox = QCheckBox()
        locked_checkbox.setChecked(True)
        locked_checkbox.setEnabled(False)
        self.table.setCellWidget(0, 2, self._centered(locked_checkbox))
        self.table.setItem(0, 3, self._locked_item(""))

        for segment in self.segments:
            row = segment.index + 1

            self.table.setItem(row, 0, self._readonly_item(segment.raw_value))

            line_edit = QLineEdit(segment.column_name)
            line_edit.textChanged.connect(
                lambda text, seg=segment: setattr(seg, "column_name", text)
            )
            self.table.setCellWidget(row, 1, line_edit)

            checkbox = QCheckBox()
            checkbox.setChecked(segment.include)
            checkbox.toggled.connect(
                lambda checked, seg=segment: setattr(seg, "include", checked)
            )
            self.table.setCellWidget(row, 2, self._centered(checkbox))

            radio = QRadioButton()
            radio.setAutoExclusive(False)  # so clicking a checked radio can uncheck it
            radio.setChecked(segment.index == self.object_id_row_index)
            radio.toggled.connect(
                lambda checked, seg=segment: self.on_object_id_toggled(seg.index, checked)
            )
            self._object_id_radios[segment.index] = radio
            self.table.setCellWidget(row, 3, self._centered(radio))

        self.table.resizeColumnToContents(0)
        self.table.resizeColumnToContents(2)
        self.table.resizeColumnToContents(3)

    def on_object_id_toggled(self, segment_index, checked):
        """Radios aren't in an exclusive QButtonGroup (see setAutoExclusive
        above) specifically so the object id flag can be optional -- clicking
        the currently-flagged radio clears it back to "none set" instead of
        being stuck permanently checked. Exclusivity across rows (at most one
        flagged) is enforced here by hand instead.
        """
        if checked:
            self.object_id_row_index = segment_index
            for other_index, other_radio in self._object_id_radios.items():
                if other_index != segment_index and other_radio.isChecked():
                    other_radio.blockSignals(True)
                    other_radio.setChecked(False)
                    other_radio.blockSignals(False)
        elif self.object_id_row_index == segment_index:
            self.object_id_row_index = None

    # -------------------------------------------------------- folder pick
    def on_browse_input(self):
        folder = QFileDialog.getExistingDirectory(self, "Select input folder")
        if not folder:
            return

        try:
            files = find_input_files(folder)
        except SegMetricError as exc:
            self._show_error(str(exc))
            return

        self.input_folder = folder
        self.input_line.setText(folder)
        self._log(f"Found {len(files)} file(s) in {folder}.")
        self._set_segments_from_text(files[0], os.path.basename(files[0]))

    # ------------------------------------------------------- manual entry
    def on_manual_filename_changed(self):
        text = self.manual_name_edit.text().strip()
        if not text:
            return
        self.input_folder = None
        self._set_segments_from_text(text, text)

    # ------------------------------------------------------------ presets
    def on_save_preset(self):
        if not self.segments:
            self._show_error(
                "Provide a sample filename first — browse to a folder or "
                "type one manually."
            )
            return

        name = self.preset_name_edit.text().strip()
        if not name:
            self._show_error("Enter a preset name before saving.")
            return

        object_id_column = None
        for segment in self.segments:
            if segment.index == self.object_id_row_index:
                object_id_column = segment.column_name
                break

        preset = Preset(
            name=name,
            segments=list(self.segments),
            object_id_column=object_id_column,
        )

        path, _ = QFileDialog.getSaveFileName(
            self, "Save preset", f"{name}.json", "JSON files (*.json)"
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"

        try:
            save_preset(path, preset)
        except SegMetricError as exc:
            self._show_error(str(exc))
            return

        self._log(f"Preset saved to {path}")

    def on_load_preset(self):
        if not self.segments:
            self._show_error(
                "Provide a sample filename first — browse to a folder or "
                "type one manually."
            )
            return

        path, _ = QFileDialog.getOpenFileName(
            self, "Load preset", "", "JSON files (*.json)"
        )
        if not path:
            return

        try:
            preset = load_preset(path)
        except SegMetricError as exc:
            self._show_error(str(exc))
            return

        updated_segments, object_id_column, warnings = apply_preset(
            self.segments, preset
        )
        self.segments = updated_segments
        self.object_id_row_index = None
        if object_id_column is not None:
            for segment in self.segments:
                if segment.column_name == object_id_column:
                    self.object_id_row_index = segment.index
                    break

        self.preset_name_edit.setText(preset.name)
        self._rebuild_table()
        self._update_button_states()

        self._log(f"Preset loaded from {path}")
        for warning in warnings:
            self._log(f"  Note: {warning}")
