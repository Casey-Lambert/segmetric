from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from segmetric.errors import SegMetricError
from segmetric.set.core.presets import load_preset

BATCH_SINGLE = "single"
BATCH_MIXED = "mixed"


class SetupPage(QWidget):
    """§1-2: required Scales file + Crops folder, optional Metadata preset,
    and the single-type/mixed-anatomy choice. Mixed-anatomy is blocked
    until a preset with an object-id column is loaded.
    """

    ready_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scales_file = None
        self.crops_folder = None
        self.metadata_preset = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        inputs_group = QGroupBox("Setup")
        inputs_layout = QFormLayout(inputs_group)

        self.scales_line = QLineEdit()
        self.scales_line.setReadOnly(True)
        scales_browse = QPushButton("Browse…")
        scales_browse.clicked.connect(self.on_browse_scales)
        scales_row = QHBoxLayout()
        scales_row.addWidget(self.scales_line)
        scales_row.addWidget(scales_browse)
        inputs_layout.addRow("Scales file (required):", scales_row)

        scales_hint = QLabel(
            "upload either scales.csv (segmetric.scale) or summary.csv (segmetric.prepare) "
        )
        scales_hint.setStyleSheet("color: gray;")
        inputs_layout.addRow("", scales_hint)

        self.crops_line = QLineEdit()
        self.crops_line.setReadOnly(True)
        crops_browse = QPushButton("Browse…")
        crops_browse.clicked.connect(self.on_browse_crops)
        crops_row = QHBoxLayout()
        crops_row.addWidget(self.crops_line)
        crops_row.addWidget(crops_browse)
        inputs_layout.addRow("Crops folder (required):", crops_row)

        self.preset_line = QLineEdit()
        self.preset_line.setReadOnly(True)
        preset_browse = QPushButton("Load…")
        preset_browse.clicked.connect(self.on_browse_preset)
        preset_clear = QPushButton("Clear")
        preset_clear.clicked.connect(self.on_clear_preset)
        preset_row = QHBoxLayout()
        preset_row.addWidget(self.preset_line)
        preset_row.addWidget(preset_browse)
        preset_row.addWidget(preset_clear)
        inputs_layout.addRow("Metadata preset (optional):", preset_row)

        preset_hint = QLabel(
            "Generated using segmetric.set - provides Object ID "
        )
        preset_hint.setStyleSheet("color: gray;")
        preset_hint.setWordWrap(True)
        inputs_layout.addRow("", preset_hint)

        self.preset_status_label = QLabel("No preset loaded.")
        inputs_layout.addRow("", self.preset_status_label)

        layout.addWidget(inputs_group)

        batch_group = QGroupBox("Batch type")
        batch_layout = QVBoxLayout(batch_group)
        self.single_radio = QRadioButton(
            "Single Object - apply one filter for all images"
        )
        self.single_radio.setChecked(True)
        self.mixed_radio = QRadioButton(
            "Mixed Object - apply filters based on Object ID"
        )
        batch_button_group = QButtonGroup(batch_group)
        batch_button_group.addButton(self.single_radio)
        batch_button_group.addButton(self.mixed_radio)
        self.single_radio.toggled.connect(self._on_batch_type_changed)
        self.mixed_radio.toggled.connect(self._on_batch_type_changed)
        batch_layout.addWidget(self.single_radio)
        batch_layout.addWidget(self.mixed_radio)

        self.mixed_warning_label = QLabel(
            "⚠ Mixed-batches require a metadata preset with an "
            "object-id column assigned. Load one above, or switch to "
            "single-type."
        )
        self.mixed_warning_label.setStyleSheet("color: #b00000;")
        self.mixed_warning_label.setWordWrap(True)
        self.mixed_warning_label.setVisible(False)
        batch_layout.addWidget(self.mixed_warning_label)

        layout.addWidget(batch_group)
        layout.addStretch(1)

    # -------------------------------------------------------------- state
    def batch_type(self):
        return BATCH_MIXED if self.mixed_radio.isChecked() else BATCH_SINGLE

    def is_ready(self):
        if not (self.scales_file and self.crops_folder):
            return False
        if self.batch_type() == BATCH_MIXED and not self._preset_has_object_id():
            return False
        return True

    def _preset_has_object_id(self):
        return self.metadata_preset is not None and self.metadata_preset.object_id_column is not None

    def _emit_ready(self):
        self.mixed_warning_label.setVisible(
            self.batch_type() == BATCH_MIXED and not self._preset_has_object_id()
        )
        self.ready_changed.emit(self.is_ready())

    def _on_batch_type_changed(self, _checked):
        self._emit_ready()

    # -------------------------------------------------------------- browse
    def on_browse_scales(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select scales file", "", "CSV files (*.csv)")
        if not path:
            return
        self.scales_file = path
        self.scales_line.setText(path)
        self._emit_ready()

    def on_browse_crops(self):
        folder = QFileDialog.getExistingDirectory(self, "Select crops folder")
        if not folder:
            return
        self.crops_folder = folder
        self.crops_line.setText(folder)
        self._emit_ready()

    def on_browse_preset(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load metadata preset", "", "JSON files (*.json)"
        )
        if not path:
            return
        try:
            preset = load_preset(path)
        except SegMetricError as exc:
            QMessageBox.critical(self, "SegMetric.Mask — Error", str(exc))
            return
        self.metadata_preset = preset
        self.preset_line.setText(path)
        object_id_note = (
            f"object-id column: {preset.object_id_column}"
            if preset.object_id_column
            else "no object-id column assigned"
        )
        self.preset_status_label.setText(f"Loaded '{preset.name}' ({object_id_note}).")
        self._emit_ready()

    def on_clear_preset(self):
        self.metadata_preset = None
        self.preset_line.clear()
        self.preset_status_label.setText("No preset loaded.")
        self._emit_ready()
