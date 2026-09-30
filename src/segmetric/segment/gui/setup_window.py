

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from segmetric.errors import SegMetricError
from segmetric.prepare.core.metadata import apply_preset_to_filename
from segmetric.set.core.presets import load_preset

from ..core.matching import match_crops

BATCH_SINGLE = "single"
BATCH_MIXED = "mixed"


class SetupPage(QWidget):
    """Required Scales file + Crops folder
    """

    ready_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scales_file = None
        self.crops_folder = None
        self.masks_folder = None
        self.metadata_preset = None
        self._discovered_object_ids = []
        self._object_id_checkboxes = {}
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)
        content = QWidget()
        layout = QVBoxLayout(content)

        inputs_group = QGroupBox("Inputs")
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
            "upload scales.csv (segmetric.scale) or summary.csv (segmetric.prepare) "
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

        self.masks_line = QLineEdit()
        self.masks_line.setReadOnly(True)
        masks_browse = QPushButton("Browse…")
        masks_browse.clicked.connect(self.on_browse_masks)
        masks_clear = QPushButton("Clear")
        masks_clear.clicked.connect(self.on_clear_masks)
        masks_row = QHBoxLayout()
        masks_row.addWidget(self.masks_line)
        masks_row.addWidget(masks_browse)
        masks_row.addWidget(masks_clear)
        inputs_layout.addRow("Masks folder (recommended):", masks_row)

        masks_hint = QLabel(
            "segmetric.mask output (recomended)"
            "If no mask file provided, defualts to using entire image area "
        )
        masks_hint.setStyleSheet("color: #b06a00;")
        masks_hint.setWordWrap(True)
        inputs_layout.addRow("", masks_hint)

        self.remove_blank_checkbox = QCheckBox("Remove files tagged _blank")
        self.remove_blank_checkbox.setChecked(True)
        self.remove_blank_checkbox.toggled.connect(self._on_inputs_changed)
        inputs_layout.addRow("", self.remove_blank_checkbox)

        blank_hint = QLabel(
            "_blank files dropped from batch processing"
        )
        blank_hint.setStyleSheet("color: gray;")
        blank_hint.setWordWrap(True)
        inputs_layout.addRow("", blank_hint)

        self.mask_warning_label = QLabel("")
        self.mask_warning_label.setStyleSheet("color: #b06a00;")
        self.mask_warning_label.setWordWrap(True)
        inputs_layout.addRow("", self.mask_warning_label)

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
            "Generated with segmetric.set or segmetric.prepare "
            "enables use of Object ID to apply filters"
        )
        preset_hint.setStyleSheet("color: gray;")
        preset_hint.setWordWrap(True)
        inputs_layout.addRow("", preset_hint)

        self.preset_status_label = QLabel("No preset loaded.")
        inputs_layout.addRow("", self.preset_status_label)

        layout.addWidget(inputs_group)

        self.object_id_filter_group = QGroupBox("Object-ID filter (optional)")
        self.object_id_filter_group.setVisible(False)
        object_id_filter_layout = QVBoxLayout(self.object_id_filter_group)
        object_id_filter_layout.addWidget(
            QLabel("Only process crops with these object ids (all checked by default):")
        )
        self.object_ids_container = QWidget()
        self.object_ids_layout = QVBoxLayout(self.object_ids_container)
        object_id_filter_layout.addWidget(self.object_ids_container)
        layout.addWidget(self.object_id_filter_group)

        batch_group = QGroupBox("Batch type")
        batch_layout = QVBoxLayout(batch_group)
        self.single_radio = QRadioButton("Single Object - apply one filter for all images")
        self.single_radio.setChecked(True)
        self.mixed_radio = QRadioButton(
            "Mixed Object - apply filters based on Object ID "
        )
        batch_button_group = QButtonGroup(batch_group)
        batch_button_group.addButton(self.single_radio)
        batch_button_group.addButton(self.mixed_radio)
        self.single_radio.toggled.connect(self._on_inputs_changed)
        self.mixed_radio.toggled.connect(self._on_inputs_changed)
        batch_layout.addWidget(self.single_radio)
        batch_layout.addWidget(self.mixed_radio)

        self.mixed_warning_label = QLabel(
            "⚠ Mixed-batches require Object ID from metadata file"
            "column assigned. Load one above, or switch to single-batch."
        )
        self.mixed_warning_label.setStyleSheet("color: #b00000;")
        self.mixed_warning_label.setWordWrap(True)
        self.mixed_warning_label.setVisible(False)
        batch_layout.addWidget(self.mixed_warning_label)

        layout.addWidget(batch_group)
        layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        outer.addWidget(scroll)

    # ---------------------------------------------------------
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

    def selected_object_ids(self):
        """None if there's no object-id filter active at all (nothing to
        filter by); otherwise the set of object ids currently checked.
        """
        if not self._object_id_checkboxes:
            return None
        return {oid for oid, cb in self._object_id_checkboxes.items() if cb.isChecked()}

    def _emit_ready(self):
        self.mixed_warning_label.setVisible(
            self.batch_type() == BATCH_MIXED and not self._preset_has_object_id()
        )
        self.ready_changed.emit(self.is_ready())

    def _on_inputs_changed(self, *_args):
        self._refresh_object_id_filter()
        self._emit_ready()

    #------------------------------------------------------------- file selection 
    def on_browse_scales(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select scales file", "", "CSV files (*.csv)")
        if not path:
            return
        self.scales_file = path
        self.scales_line.setText(path)
        self._on_inputs_changed()

    def on_browse_crops(self):
        folder = QFileDialog.getExistingDirectory(self, "Select crops folder")
        if not folder:
            return
        self.crops_folder = folder
        self.crops_line.setText(folder)
        self._on_inputs_changed()

    def on_browse_masks(self):
        folder = QFileDialog.getExistingDirectory(self, "Select masks folder")
        if not folder:
            return
        self.masks_folder = folder
        self.masks_line.setText(folder)
        self._on_inputs_changed()

    def on_clear_masks(self):
        self.masks_folder = None
        self.masks_line.clear()
        self._on_inputs_changed()

    def on_browse_preset(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load metadata preset", "", "JSON files (*.json)"
        )
        if not path:
            return
        try:
            preset = load_preset(path)
        except SegMetricError as exc:
            QMessageBox.critical(self, "SegMetric.Segment — Error", str(exc))
            return
        self.metadata_preset = preset
        self.preset_line.setText(path)
        object_id_note = (
            f"object-id column: {preset.object_id_column}"
            if preset.object_id_column
            else "no object-id column assigned"
        )
        self.preset_status_label.setText(f"Loaded '{preset.name}' ({object_id_note}).")
        self._on_inputs_changed()

    def on_clear_preset(self):
        self.metadata_preset = None
        self.preset_line.clear()
        self.preset_status_label.setText("No preset loaded.")
        self._on_inputs_changed()

    #--------------------------------------------------- using preset 'object-id'
    def _refresh_object_id_filter(self):
        self.mask_warning_label.setText("")
        ready_for_scan = self.scales_file and self.crops_folder and self._preset_has_object_id()
        self.object_id_filter_group.setVisible(bool(ready_for_scan))
        if not ready_for_scan:
            self._discovered_object_ids = []
            self._object_id_checkboxes = {}
            self._clear_object_ids_layout()
            return

        try:
            matched, _unmatched, no_mask = match_crops(
                self.crops_folder,
                self.scales_file,
                self.masks_folder,
                exclude_blank_tagged=self.remove_blank_checkbox.isChecked(),
            )
        except SegMetricError:
            return  # surfaced properly when Next is actually clicked

        if self.masks_folder and no_mask:
            self.mask_warning_label.setText(
                f"⚠ {len(no_mask)} of {len(matched)} matched crop(s) have no usable "
                "mask and will fall back to segmenting the whole image."
            )

        counts = {}
        for item in matched:
            row = apply_preset_to_filename(item.original_stem, self.metadata_preset)
            object_id = row.get(self.metadata_preset.object_id_column)
            if object_id:
                counts[object_id] = counts.get(object_id, 0) + 1

        if list(counts.keys()) == self._discovered_object_ids and self._object_id_checkboxes:
            return  

        self._discovered_object_ids = sorted(counts)
        self._rebuild_object_ids_layout(counts)


    def _clear_object_ids_layout(self):
        while self.object_ids_layout.count():
            item = self.object_ids_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _rebuild_object_ids_layout(self, counts):
        self._clear_object_ids_layout()
        self._object_id_checkboxes = {}
        for object_id in sorted(counts):
            cb = QCheckBox(f"{object_id} ({counts[object_id]})")
            cb.setChecked(True)
            self.object_ids_layout.addWidget(cb)
            self._object_id_checkboxes[object_id] = cb


