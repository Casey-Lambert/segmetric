

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from segmetric.errors import SegMetricError

from ..core.model import BLANK_PRESET, DEFAULT_PRESETS, DetectionSettings, SegmentPreset
from ..core.presets import load_segment_preset, save_segment_preset

_STARTING_POINTS = ["Forewing Cell", "Leg Segments", "Blank"]


class SegmentPresetEditorWidget(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self.start_buttons["Forewing Cell"].setChecked(True)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Preset name:"))
        self.name_edit = QLineEdit()
        name_row.addWidget(self.name_edit)
        layout.addLayout(name_row)

        start_group = QGroupBox("Start from")
        start_layout = QHBoxLayout(start_group)
        self.start_buttons = {}
        button_group = QButtonGroup(start_group)
        for label in _STARTING_POINTS:
            btn = QRadioButton(label)
            button_group.addButton(btn)
            start_layout.addWidget(btn)
            btn.toggled.connect(self._make_start_handler(label))
            self.start_buttons[label] = btn
        layout.addWidget(start_group)

        layout.addWidget(self._build_steps_group())
        layout.addWidget(self._build_detection_group())

        preset_row = QHBoxLayout()
        self.load_preset_btn = QPushButton("Load Preset…")
        self.load_preset_btn.clicked.connect(self.on_load_preset)
        self.save_preset_btn = QPushButton("Save Preset…")
        self.save_preset_btn.clicked.connect(self.on_save_preset)
        preset_row.addWidget(self.load_preset_btn)
        preset_row.addWidget(self.save_preset_btn)
        layout.addLayout(preset_row)

        layout.addStretch(1)

    def _build_steps_group(self):
        group = QGroupBox("Click-select steps (in order)")
        layout = QVBoxLayout(group)

        hint = QLabel(
            " "
        )
        hint.setStyleSheet("color: gray;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.steps_list = QListWidget()
        self.steps_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.steps_list.itemChanged.connect(self._on_step_renamed)
        layout.addWidget(self.steps_list)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add Step")
        add_btn.clicked.connect(self.on_add_step)
        remove_btn = QPushButton("Remove Step")
        remove_btn.clicked.connect(self.on_remove_step)
        up_btn = QPushButton("Move Up")
        up_btn.clicked.connect(self.on_move_step_up)
        down_btn = QPushButton("Move Down")
        down_btn.clicked.connect(self.on_move_step_down)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(remove_btn)
        btn_row.addWidget(up_btn)
        btn_row.addWidget(down_btn)
        layout.addLayout(btn_row)

        return group

    def _build_detection_group(self):
        group = QGroupBox("Detection thresholds")
        layout = QFormLayout(group)

        self.sigma_min_spin = self._float_spin(0.1, 50.0)
        layout.addRow("Sato sigma min:", self.sigma_min_spin)

        self.sigma_max_spin = self._float_spin(0.1, 50.0)
        layout.addRow("Sato sigma max:", self.sigma_max_spin)

        self.block_size_spin = QSpinBox()
        self.block_size_spin.setRange(3, 999)
        self.block_size_spin.setSingleStep(2)  # must stay odd
        layout.addRow("Local threshold block size (odd):", self.block_size_spin)

        self.offset_spin = self._float_spin(-5.0, 5.0, decimals=3, step=0.01)
        layout.addRow("Local threshold offset:", self.offset_spin)

        self.close_px_spin = QSpinBox()
        self.close_px_spin.setRange(1, 99)
        layout.addRow("Vein close (px):", self.close_px_spin)

        self.min_vein_spin = QSpinBox()
        self.min_vein_spin.setRange(0, 1_000_000)
        layout.addRow("Min vein size (px²):", self.min_vein_spin)

        self.gaussian_sigma_spin = self._float_spin(0.0, 50.0)
        layout.addRow("Distance-transform smoothing:", self.gaussian_sigma_spin)

        self.h_maxima_spin = self._float_spin(0.0, 255.0)
        layout.addRow("Seed prominence (h-maxima):", self.h_maxima_spin)

        return group

    def _float_spin(self, lo, hi, decimals=2, step=0.1):
        spin = QDoubleSpinBox()
        spin.setRange(lo, hi)
        spin.setDecimals(decimals)
        spin.setSingleStep(step)
        return spin

    #------------------------------------------------------------- Starting
    def _make_start_handler(self, label):
        def handler(checked):
            if checked:
                self._apply_starting_point(label)

        return handler

    def _apply_starting_point(self, label):
        preset = BLANK_PRESET if label == "Blank" else DEFAULT_PRESETS[label]
        self.load_settings(preset)

    #-------------------------------------------------------------- making steps
    def _current_steps(self):
        return [self.steps_list.item(i).text() for i in range(self.steps_list.count())]

    def _set_steps(self, steps):
        self.steps_list.blockSignals(True)
        self.steps_list.clear()
        for step in steps:
            self.steps_list.addItem(step)
        for i in range(self.steps_list.count()):
            it = self.steps_list.item(i)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsEditable)
        self.steps_list.blockSignals(False)

    def on_add_step(self):
        text, ok = QInputDialog.getText(self, "Add step", "Step name:")
        text = text.strip().lstrip("_").replace(" ", "_")
        if not ok or not text:
            return
        steps = self._current_steps()
        steps.append(text)
        self._set_steps(steps)

    def on_remove_step(self):
        row = self.steps_list.currentRow()
        if row < 0:
            return
        if self.steps_list.count() <= 1:
            QMessageBox.warning(self, "SegMetric.Segment", "A preset needs at least one step.")
            return
        self.steps_list.takeItem(row)

    def on_move_step_up(self):
        row = self.steps_list.currentRow()
        if row <= 0:
            return
        item = self.steps_list.takeItem(row)
        self.steps_list.insertItem(row - 1, item)
        self.steps_list.setCurrentRow(row - 1)

    def on_move_step_down(self):
        row = self.steps_list.currentRow()
        if row < 0 or row >= self.steps_list.count() - 1:
            return
        item = self.steps_list.takeItem(row)
        self.steps_list.insertItem(row + 1, item)
        self.steps_list.setCurrentRow(row + 1)

    def _on_step_renamed(self, item):
        text = item.text().strip().lstrip("_").replace(" ", "_")
        item.setText(text or "step")

    #---------------------------------------------------
    def current_preset(self) -> SegmentPreset:
        return SegmentPreset(
            name=self.name_edit.text().strip() or "Custom",
            steps=self._current_steps() or ["step_1"],
            detection=DetectionSettings(
                sato_sigma_min=self.sigma_min_spin.value(),
                sato_sigma_max=self.sigma_max_spin.value(),
                local_thresh_block_size=self.block_size_spin.value(),
                local_thresh_offset=self.offset_spin.value(),
                vein_close_px=self.close_px_spin.value(),
                min_vein_size=self.min_vein_spin.value(),
                distance_gaussian_sigma=self.gaussian_sigma_spin.value(),
                h_maxima_h=self.h_maxima_spin.value(),
            ),
        )

    def load_settings(self, preset: SegmentPreset):
        for btn in self.start_buttons.values():
            btn.blockSignals(True)
            btn.setChecked(False)
            btn.blockSignals(False)
        self.name_edit.setText(preset.name or "Custom")
        self._set_steps(preset.steps)
        d = preset.detection
        self.sigma_min_spin.setValue(d.sato_sigma_min)
        self.sigma_max_spin.setValue(d.sato_sigma_max)
        self.block_size_spin.setValue(d.local_thresh_block_size)
        self.offset_spin.setValue(d.local_thresh_offset)
        self.close_px_spin.setValue(d.vein_close_px)
        self.min_vein_spin.setValue(d.min_vein_size)
        self.gaussian_sigma_spin.setValue(d.distance_gaussian_sigma)
        self.h_maxima_spin.setValue(d.h_maxima_h)

    #-----------------------------------------------------------presets
    def on_load_preset(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load preset", "", "JSON files (*.json)")
        if not path:
            return
        try:
            preset = load_segment_preset(path)
        except SegMetricError as exc:
            QMessageBox.critical(self, "SegMetric.Segment — Error", str(exc))
            return
        self.load_settings(preset)

    def on_save_preset(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save preset", "segment_preset.json", "JSON files (*.json)"
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            save_segment_preset(path, self.current_preset())
        except SegMetricError as exc:
            QMessageBox.critical(self, "SegMetric.Segment — Error", str(exc))




