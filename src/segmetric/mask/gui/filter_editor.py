from PyQt6.QtWidgets import (
    QButtonGroup,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from segmetric.errors import SegMetricError

from ..core.model import BLANK_FILTER, DEFAULT_FILTERS, FilterSettings
from ..core.presets import load_filter_preset, save_filter_preset

_STARTING_POINTS = ["Forewing", "Hindwing", "Leg", "Blank"]


class FilterEditorWidget(QWidget):
    """Reusable filter picker + editor -- covers all 4 of §3's filter-setup
    options: pick a default (1), pick a default then edit the spin boxes
    (2), load a custom filter from disk (3), or start from the Blank
    template and edit (4). Used both for the single-type batch flow and,
    embedded once per group, in the mixed-anatomy assignment screen.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()
        self.start_buttons["Forewing"].setChecked(True)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Filter name:"))
        self.name_edit = QLineEdit()
        name_row.addWidget(self.name_edit)
        layout.addLayout(name_row)

        start_group = QGroupBox("Start from")
        start_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
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

        params_group = QGroupBox("Filter parameters")
        params_layout = QFormLayout(params_group)

        self.first_pass_factor_spin = self._make_float_spin(0.0, 1.0)
        params_layout.addRow("First-pass factor:", self.first_pass_factor_spin)

        self.normal_thresh_spin = self._make_float_spin(0.0, 1.0)
        params_layout.addRow("Normal threshold:", self.normal_thresh_spin)

        self.vein_thresh_spin = self._make_float_spin(0.0, 1.0)
        params_layout.addRow("Vein threshold:", self.vein_thresh_spin)

        self.erode_px_spin = self._make_int_spin(0, 999)
        params_layout.addRow("Erode (px):", self.erode_px_spin)

        self.close_px_spin = self._make_int_spin(0, 999)
        params_layout.addRow("Close (px):", self.close_px_spin)

        self.fourier_freq_spin = self._make_float_spin(0.0, 1.0, decimals=3, step=0.005)
        params_layout.addRow("Fourier smoothing:", self.fourier_freq_spin)

        self.min_blob_spin = self._make_int_spin(0, 1_000_000)
        params_layout.addRow("Min blob (px²):", self.min_blob_spin)

        layout.addWidget(params_group)

        preset_row = QHBoxLayout()
        self.load_preset_btn = QPushButton("Load Filter Preset…")
        self.load_preset_btn.clicked.connect(self.on_load_preset)
        self.save_preset_btn = QPushButton("Save Filter Preset…")
        self.save_preset_btn.clicked.connect(self.on_save_preset)
        preset_row.addWidget(self.load_preset_btn)
        preset_row.addWidget(self.save_preset_btn)
        layout.addLayout(preset_row)

        self.blank_warning = QLabel(
            "⚠ Starting from Blank -- all values are placeholders. Tune them "
            "before running."
        )
        self.blank_warning.setStyleSheet("color: #b06a00;")
        self.blank_warning.setWordWrap(True)
        self.blank_warning.setVisible(False)
        layout.addWidget(self.blank_warning)

        layout.addStretch(1)

    def _make_float_spin(self, lo, hi, decimals=3, step=0.01):
        spin = QDoubleSpinBox()
        spin.setRange(lo, hi)
        spin.setDecimals(decimals)
        spin.setSingleStep(step)
        return spin

    def _make_int_spin(self, lo, hi):
        spin = QSpinBox()
        spin.setRange(lo, hi)
        return spin

    def _make_start_handler(self, label):
        def handler(checked):
            if checked:
                self._apply_starting_point(label)

        return handler

    def _apply_starting_point(self, label):
        settings = BLANK_FILTER if label == "Blank" else DEFAULT_FILTERS[label]
        self._set_spin_values(settings)
        self.name_edit.setText(settings.name)
        self.blank_warning.setVisible(label == "Blank")

    def _set_spin_values(self, settings: FilterSettings):
        self.first_pass_factor_spin.setValue(settings.first_pass_factor)
        self.normal_thresh_spin.setValue(settings.normal_thresh)
        self.vein_thresh_spin.setValue(settings.vein_thresh)
        self.erode_px_spin.setValue(settings.erode_px)
        self.close_px_spin.setValue(settings.close_px)
        self.fourier_freq_spin.setValue(settings.fourier_freq)
        self.min_blob_spin.setValue(settings.min_blob)

    # -------------------------------------------------------------- state
    def current_settings(self) -> FilterSettings:
        return FilterSettings(
            first_pass_factor=self.first_pass_factor_spin.value(),
            normal_thresh=self.normal_thresh_spin.value(),
            vein_thresh=self.vein_thresh_spin.value(),
            erode_px=self.erode_px_spin.value(),
            close_px=self.close_px_spin.value(),
            fourier_freq=self.fourier_freq_spin.value(),
            min_blob=self.min_blob_spin.value(),
            name=self.name_edit.text().strip() or "Custom",
        )

    def load_settings(self, settings: FilterSettings):
        """Populate the editor from settings without touching the 'Start
        from' radio selection (used for loading a custom/blank preset from
        disk, or restoring a saved mixed-anatomy group).
        """
        for btn in self.start_buttons.values():
            btn.blockSignals(True)
            btn.setChecked(False)
            btn.blockSignals(False)
        self._set_spin_values(settings)
        self.name_edit.setText(settings.name or "Custom")
        self.blank_warning.setVisible(False)

    def set_enabled(self, enabled):
        self.setEnabled(enabled)

    # -------------------------------------------------------------- presets
    def on_load_preset(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load filter preset", "", "JSON files (*.json)"
        )
        if not path:
            return
        try:
            settings = load_filter_preset(path)
        except SegMetricError as exc:
            QMessageBox.critical(self, "SegMetric.Mask — Error", str(exc))
            return
        self.load_settings(settings)

    def on_save_preset(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save filter preset", "filter_preset.json", "JSON files (*.json)"
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            save_filter_preset(path, self.current_settings())
        except SegMetricError as exc:
            QMessageBox.critical(self, "SegMetric.Mask — Error", str(exc))
