import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from segmetric.errors import SegMetricError
from segmetric.tag.core.discovery import find_input_files

from ..core.model import ScaleSettings
from ..core.pipeline import SCALE_SOURCE_MANUAL, SCALE_SOURCE_MANUAL_BATCH
from ..core.presets import load_scale_preset, save_scale_preset
from .manual_crop_dialog import CropReviewDialog, SetCropDialog
from .manual_scale_dialog import ScaleReviewDialog, SetScaleDialog
from .preview import bgr_to_qpixmap, load_preview_image, render_marker_preview
from .worker import ManualScaleJobWorker, ScaleJobWorker

DEFAULTS = ScaleSettings()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SegMetric.Scale — ArUco Scale & Crop")
        self.resize(1200, 760)

        self.input_folder = None
        self.output_folder = None
        self.first_input_file = None
        self.preview_image_bgr = None

        self.scale_worker = None

        # No-markers manual mode -- see _build_manual_controls/on_set_scale/
        # on_set_crop. _manual_crop_bbox_by_name stays None both before any
        # crop is configured and whenever "No crop" is selected; on_run
        # only treats it as "no cropping" when the no-crop radio itself is
        # checked (see _effective_crop_bbox_by_name), so switching crop
        # modes never accidentally reuses a stale configuration.
        self._manual_scale_by_name = {}
        self._manual_scale_source_by_name = {}
        self._manual_crop_bbox_by_name = None

        self._build_ui()
        self._update_run_button_state()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)

        controls_scroll = QScrollArea()
        controls_scroll.setWidgetResizable(True)
        controls_scroll.setWidget(self._build_controls())
        controls_scroll.setMinimumWidth(460)
        controls_scroll.setMaximumWidth(560)
        splitter.addWidget(controls_scroll)

        splitter.addWidget(self._build_preview())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(splitter)

    def _build_controls(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)

        # -- folders --
        folders_group = QGroupBox("Folders")
        folders_layout = QFormLayout(folders_group)

        self.input_line = QLineEdit()
        self.input_line.setReadOnly(True)
        input_browse = QPushButton("Browse…")
        input_browse.clicked.connect(self.on_browse_input)
        input_row = QHBoxLayout()
        input_row.addWidget(self.input_line)
        input_row.addWidget(input_browse)
        folders_layout.addRow("Input folder:", input_row)

        self.output_line = QLineEdit()
        self.output_line.setReadOnly(True)
        output_browse = QPushButton("Browse…")
        output_browse.clicked.connect(self.on_browse_output)
        output_row = QHBoxLayout()
        output_row.addWidget(self.output_line)
        output_row.addWidget(output_browse)
        folders_layout.addRow("Output folder:", output_row)

        layout.addWidget(folders_group)

        # -- marker mode --
        layout.addWidget(self._build_marker_mode_controls())

        # -- output format --
        format_group = QGroupBox("Output format")
        format_layout = QHBoxLayout(format_group)
        self.tiff_radio = QRadioButton("TIFF (recommended)")
        self.tiff_radio.setChecked(True)
        self.png_radio = QRadioButton("PNG")
        self.output_format_group = QButtonGroup(format_group)
        self.output_format_group.addButton(self.tiff_radio)
        self.output_format_group.addButton(self.png_radio)
        format_layout.addWidget(self.tiff_radio)
        format_layout.addWidget(self.png_radio)
        layout.addWidget(format_group)

        # -- scale --
        self.scale_group = QGroupBox("Scale")
        scale_layout = QFormLayout(self.scale_group)

        self.spacing_spin = QDoubleSpinBox()
        self.spacing_spin.setRange(0.01, 1000.0)
        self.spacing_spin.setDecimals(3)
        self.spacing_spin.setSuffix(" mm")
        self.spacing_spin.setValue(DEFAULTS.marker_spacing_mm)
        self.spacing_spin.valueChanged.connect(self.on_settings_changed)
        scale_layout.addRow("Marker spacing:", self.spacing_spin)

        spacing_hint = QLabel("Distance between ArUco marker centers")
        spacing_hint.setStyleSheet("color: gray;")
        spacing_hint.setWordWrap(True)
        scale_layout.addRow("", spacing_hint)

        self.blob_fallback_checkbox = QCheckBox("Use blob-detection fallback")
        self.blob_fallback_checkbox.setChecked(DEFAULTS.use_blob_fallback)
        self.blob_fallback_checkbox.toggled.connect(self.on_settings_changed)
        scale_layout.addRow("", self.blob_fallback_checkbox)

        blob_hint = QLabel(
            "If ArUco decoding finds fewer than 4 markers, use plain shape "
            "detection."
        )
        blob_hint.setStyleSheet("color: gray;")
        blob_hint.setWordWrap(True)
        scale_layout.addRow("", blob_hint)

        layout.addWidget(self.scale_group)

        # -- crop region (relative to markers) --
        self.crop_region_group = self._build_crop_region_controls()
        layout.addWidget(self.crop_region_group)

        # -- thresholds (advanced) --
        self.threshold_wrapper = self._build_threshold_controls()
        layout.addWidget(self.threshold_wrapper)

        # -- blob fallback tuning (advanced) --
        self.blob_wrapper = self._build_blob_controls()
        layout.addWidget(self.blob_wrapper)

        # -- no-markers workflow (hidden until "Manually set scale" is picked) --
        layout.addWidget(self._build_manual_controls())

        # -- presets --
        preset_row = QHBoxLayout()
        self.save_preset_btn = QPushButton("Save Preset")
        self.save_preset_btn.clicked.connect(self.on_save_preset)
        self.load_preset_btn = QPushButton("Load Preset")
        self.load_preset_btn.clicked.connect(self.on_load_preset)
        preset_row.addWidget(self.save_preset_btn)
        preset_row.addWidget(self.load_preset_btn)
        layout.addLayout(preset_row)

        # -- run --
        self.run_btn = QPushButton("Run")
        self.run_btn.setMinimumHeight(36)
        self.run_btn.clicked.connect(self.on_run)
        layout.addWidget(self.run_btn)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)

        layout.addWidget(QLabel("Status:"))
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view, stretch=1)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setMinimumHeight(32)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("QPushButton { color: #b00000; }")
        self.stop_btn.clicked.connect(self.on_stop)
        layout.addWidget(self.stop_btn)

        panel.setMinimumWidth(440)
        panel.setMaximumWidth(540)
        return panel

    def _build_marker_mode_controls(self):
        group = QGroupBox("Image Marker")
        layout = QVBoxLayout(group)

        self.markers_present_radio = QRadioButton("Use ArUco markers")
        self.markers_present_radio.setChecked(True)
        self.no_markers_radio = QRadioButton("Manually set scale")
        mode_group = QButtonGroup(group)
        mode_group.addButton(self.markers_present_radio)
        mode_group.addButton(self.no_markers_radio)
        self.markers_present_radio.toggled.connect(self._on_marker_mode_changed)
        self.no_markers_radio.toggled.connect(self._on_marker_mode_changed)
        layout.addWidget(self.markers_present_radio)
        layout.addWidget(self.no_markers_radio)

        hint = QLabel("Set scale with 2-point calibration")
        hint.setStyleSheet("color: gray;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        return group

    def _build_manual_controls(self):
        self.manual_group = QGroupBox("No-markers workflow")
        self.manual_group.setVisible(False)
        layout = QVBoxLayout(self.manual_group)

        # -- scale --
        scale_box = QGroupBox("Scale")
        scale_layout = QVBoxLayout(scale_box)

        self.scale_batch_radio = QRadioButton("One scale for the whole batch")
        self.scale_batch_radio.setChecked(True)
        self.scale_per_image_radio = QRadioButton("Set scale for each image individually")
        scale_mode_group = QButtonGroup(scale_box)
        scale_mode_group.addButton(self.scale_batch_radio)
        scale_mode_group.addButton(self.scale_per_image_radio)
        self.scale_batch_radio.toggled.connect(self._on_scale_mode_changed)
        self.scale_per_image_radio.toggled.connect(self._on_scale_mode_changed)
        scale_layout.addWidget(self.scale_batch_radio)
        scale_layout.addWidget(self.scale_per_image_radio)

        set_scale_btn = QPushButton("Set Scale…")
        set_scale_btn.clicked.connect(self.on_set_scale)
        scale_layout.addWidget(set_scale_btn)

        self.scale_status_label = QLabel("⚠ No scale set yet.")
        self.scale_status_label.setStyleSheet("color: #b06a00;")
        self.scale_status_label.setWordWrap(True)
        scale_layout.addWidget(self.scale_status_label)

        layout.addWidget(scale_box)

        # -- crop --
        crop_box = QGroupBox("Crop region")
        crop_layout = QVBoxLayout(crop_box)

        self.no_crop_radio = QRadioButton("No crop")
        self.no_crop_radio.setChecked(True)
        self.crop_batch_radio = QRadioButton("One crop region for the whole batch")
        self.crop_per_image_radio = QRadioButton("Set crop region for each image individually")
        crop_mode_group = QButtonGroup(crop_box)
        for radio in (self.no_crop_radio, self.crop_batch_radio, self.crop_per_image_radio):
            crop_mode_group.addButton(radio)
            radio.toggled.connect(self._on_crop_mode_changed)
        crop_layout.addWidget(self.no_crop_radio)
        crop_layout.addWidget(self.crop_batch_radio)
        crop_layout.addWidget(self.crop_per_image_radio)

        self.set_crop_btn = QPushButton("Set Crop Region…")
        self.set_crop_btn.setEnabled(False)
        self.set_crop_btn.clicked.connect(self.on_set_crop)
        crop_layout.addWidget(self.set_crop_btn)

        self.crop_status_label = QLabel("No crop -- images are saved at full size.")
        self.crop_status_label.setStyleSheet("color: gray;")
        self.crop_status_label.setWordWrap(True)
        crop_layout.addWidget(self.crop_status_label)

        layout.addWidget(crop_box)

        return self.manual_group

    def _build_crop_region_controls(self):
        """Where, within the detected marker bounding box, to crop --
        structurally identical to segmetric.tag's "OCR search region"
        controls (anchor radios + a size-percentage spinbox per axis), a
        three-way anchor group instead of tag's two-way one so "center"
        (today's fixed behavior, kept as the default) is an explicit
        choice alongside growing from one edge.
        """
        group = QGroupBox("Crop")
        region_layout = QFormLayout(group)

        self.crop_v_top_radio = QRadioButton("Top")
        self.crop_v_center_radio = QRadioButton("Center")
        self.crop_v_center_radio.setChecked(True)  # matches today's fixed quarter-trim
        self.crop_v_bottom_radio = QRadioButton("Bottom")
        crop_v_anchor_group = QButtonGroup(group)
        for radio in (self.crop_v_top_radio, self.crop_v_center_radio, self.crop_v_bottom_radio):
            crop_v_anchor_group.addButton(radio)
            radio.toggled.connect(self.on_settings_changed)
        v_anchor_row = QHBoxLayout()
        v_anchor_row.addWidget(self.crop_v_top_radio)
        v_anchor_row.addWidget(self.crop_v_center_radio)
        v_anchor_row.addWidget(self.crop_v_bottom_radio)
        region_layout.addRow("From:", v_anchor_row)

        self.crop_v_size_spin = QSpinBox()
        self.crop_v_size_spin.setRange(1, 100)
        self.crop_v_size_spin.setValue(DEFAULTS.crop_v_size_pct)
        self.crop_v_size_spin.setSuffix("%")
        self.crop_v_size_spin.valueChanged.connect(self.on_settings_changed)
        region_layout.addRow("Vertical:", self.crop_v_size_spin)

        self.crop_h_left_radio = QRadioButton("Left")
        self.crop_h_center_radio = QRadioButton("Center")
        self.crop_h_center_radio.setChecked(True)  # matches today's fixed full-width
        self.crop_h_right_radio = QRadioButton("Right")
        crop_h_anchor_group = QButtonGroup(group)
        for radio in (self.crop_h_left_radio, self.crop_h_center_radio, self.crop_h_right_radio):
            crop_h_anchor_group.addButton(radio)
            radio.toggled.connect(self.on_settings_changed)
        h_anchor_row = QHBoxLayout()
        h_anchor_row.addWidget(self.crop_h_left_radio)
        h_anchor_row.addWidget(self.crop_h_center_radio)
        h_anchor_row.addWidget(self.crop_h_right_radio)
        region_layout.addRow("From:", h_anchor_row)

        self.crop_h_size_spin = QSpinBox()
        self.crop_h_size_spin.setRange(1, 100)
        self.crop_h_size_spin.setValue(DEFAULTS.crop_h_size_pct)
        self.crop_h_size_spin.setSuffix("%")
        self.crop_h_size_spin.valueChanged.connect(self.on_settings_changed)
        region_layout.addRow("Horizontal", self.crop_h_size_spin)

        return group

    def _current_crop_v_anchor(self):
        if self.crop_v_top_radio.isChecked():
            return "top"
        if self.crop_v_bottom_radio.isChecked():
            return "bottom"
        return "center"

    def _current_crop_h_anchor(self):
        if self.crop_h_left_radio.isChecked():
            return "left"
        if self.crop_h_right_radio.isChecked():
            return "right"
        return "center"

    def _set_crop_v_anchor(self, anchor):
        self.crop_v_top_radio.setChecked(anchor == "top")
        self.crop_v_bottom_radio.setChecked(anchor == "bottom")
        self.crop_v_center_radio.setChecked(anchor not in ("top", "bottom"))

    def _set_crop_h_anchor(self, anchor):
        self.crop_h_left_radio.setChecked(anchor == "left")
        self.crop_h_right_radio.setChecked(anchor == "right")
        self.crop_h_center_radio.setChecked(anchor not in ("left", "right"))

    def _build_threshold_controls(self):
        self.threshold_checkbox = QCheckBox("Customize ArCuo detection threshold")
        self.threshold_checkbox.toggled.connect(self.on_threshold_toggle)

        self.threshold_group = QGroupBox()
        self.threshold_group.setEnabled(False)
        threshold_layout = QFormLayout(self.threshold_group)

        self.thresh_constant_spin = QSpinBox()
        self.thresh_constant_spin.setRange(1, 100)
        self.thresh_constant_spin.setValue(DEFAULTS.adaptive_thresh_constant)
        self.thresh_constant_spin.valueChanged.connect(self.on_settings_changed)
        threshold_layout.addRow("Adaptive thresh constant:", self.thresh_constant_spin)

        self.win_min_spin = QSpinBox()
        self.win_min_spin.setRange(1, 999)
        self.win_min_spin.setValue(DEFAULTS.adaptive_thresh_win_size_min)
        self.win_min_spin.valueChanged.connect(self.on_settings_changed)
        threshold_layout.addRow("Win size min:", self.win_min_spin)

        threshold_layout.addRow(QLabel("<b>Prepare pass</b> (raw panel, before crop):"))

        self.prepare_win_max_spin = QSpinBox()
        self.prepare_win_max_spin.setRange(1, 999)
        self.prepare_win_max_spin.setValue(DEFAULTS.prepare_win_size_max)
        self.prepare_win_max_spin.valueChanged.connect(self.on_settings_changed)
        threshold_layout.addRow("Win size max:", self.prepare_win_max_spin)

        self.prepare_win_step_spin = QSpinBox()
        self.prepare_win_step_spin.setRange(1, 999)
        self.prepare_win_step_spin.setValue(DEFAULTS.prepare_win_size_step)
        self.prepare_win_step_spin.valueChanged.connect(self.on_settings_changed)
        threshold_layout.addRow("Win size step:", self.prepare_win_step_spin)

        self.prepare_error_correction_spin = QDoubleSpinBox()
        self.prepare_error_correction_spin.setRange(0.0, 1.0)
        self.prepare_error_correction_spin.setDecimals(2)
        self.prepare_error_correction_spin.setSingleStep(0.05)
        self.prepare_error_correction_spin.setValue(DEFAULTS.prepare_error_correction_rate)
        self.prepare_error_correction_spin.valueChanged.connect(self.on_settings_changed)
        threshold_layout.addRow("Error correction rate:", self.prepare_error_correction_spin)

        self.prepare_perspective_spin = QSpinBox()
        self.prepare_perspective_spin.setRange(1, 999)
        self.prepare_perspective_spin.setValue(DEFAULTS.prepare_perspective_remove_pixel_per_cell)
        self.prepare_perspective_spin.valueChanged.connect(self.on_settings_changed)
        threshold_layout.addRow("Perspective remove px/cell:", self.prepare_perspective_spin)

        threshold_layout.addRow(QLabel("<b>Final pass</b> (after crop + upscale):"))

        self.win_max_spin = QSpinBox()
        self.win_max_spin.setRange(1, 999)
        self.win_max_spin.setValue(DEFAULTS.adaptive_thresh_win_size_max)
        self.win_max_spin.valueChanged.connect(self.on_settings_changed)
        threshold_layout.addRow("Win size max:", self.win_max_spin)

        self.win_step_spin = QSpinBox()
        self.win_step_spin.setRange(1, 999)
        self.win_step_spin.setValue(DEFAULTS.adaptive_thresh_win_size_step)
        self.win_step_spin.valueChanged.connect(self.on_settings_changed)
        threshold_layout.addRow("Win size step:", self.win_step_spin)

        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.addWidget(self.threshold_checkbox)
        wrapper_layout.addWidget(self.threshold_group)
        return wrapper

    def _build_blob_controls(self):
        self.blob_advanced_checkbox = QCheckBox("Customize blob detection threshold")
        self.blob_advanced_checkbox.toggled.connect(self.on_blob_advanced_toggle)

        self.blob_advanced_group = QGroupBox()
        self.blob_advanced_group.setEnabled(False)
        blob_layout = QFormLayout(self.blob_advanced_group)

        self.blob_min_aspect_spin = QDoubleSpinBox()
        self.blob_min_aspect_spin.setRange(0.01, 10.0)
        self.blob_min_aspect_spin.setDecimals(2)
        self.blob_min_aspect_spin.setSingleStep(0.05)
        self.blob_min_aspect_spin.setValue(DEFAULTS.blob_min_aspect)
        self.blob_min_aspect_spin.valueChanged.connect(self.on_settings_changed)
        blob_layout.addRow("Min aspect ratio:", self.blob_min_aspect_spin)

        self.blob_max_aspect_spin = QDoubleSpinBox()
        self.blob_max_aspect_spin.setRange(0.01, 10.0)
        self.blob_max_aspect_spin.setDecimals(2)
        self.blob_max_aspect_spin.setSingleStep(0.05)
        self.blob_max_aspect_spin.setValue(DEFAULTS.blob_max_aspect)
        self.blob_max_aspect_spin.valueChanged.connect(self.on_settings_changed)
        blob_layout.addRow("Max aspect ratio:", self.blob_max_aspect_spin)

        blob_layout.addRow(QLabel("<b>Prepare pass</b> blob area (px²):"))

        self.prepare_blob_min_area_spin = QSpinBox()
        self.prepare_blob_min_area_spin.setRange(1, 100_000_000)
        self.prepare_blob_min_area_spin.setValue(DEFAULTS.prepare_blob_min_area)
        self.prepare_blob_min_area_spin.valueChanged.connect(self.on_settings_changed)
        blob_layout.addRow("Min area:", self.prepare_blob_min_area_spin)

        self.prepare_blob_max_area_spin = QSpinBox()
        self.prepare_blob_max_area_spin.setRange(1, 100_000_000)
        self.prepare_blob_max_area_spin.setValue(DEFAULTS.prepare_blob_max_area)
        self.prepare_blob_max_area_spin.valueChanged.connect(self.on_settings_changed)
        blob_layout.addRow("Max area:", self.prepare_blob_max_area_spin)

        blob_layout.addRow(QLabel("<b>Final pass</b> blob area (px²):"))

        self.final_blob_min_area_spin = QSpinBox()
        self.final_blob_min_area_spin.setRange(1, 100_000_000)
        self.final_blob_min_area_spin.setValue(DEFAULTS.final_blob_min_area)
        self.final_blob_min_area_spin.valueChanged.connect(self.on_settings_changed)
        blob_layout.addRow("Min area:", self.final_blob_min_area_spin)

        self.final_blob_max_area_spin = QSpinBox()
        self.final_blob_max_area_spin.setRange(1, 100_000_000)
        self.final_blob_max_area_spin.setValue(DEFAULTS.final_blob_max_area)
        self.final_blob_max_area_spin.valueChanged.connect(self.on_settings_changed)
        blob_layout.addRow("Max area:", self.final_blob_max_area_spin)

        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.addWidget(self.blob_advanced_checkbox)
        wrapper_layout.addWidget(self.blob_advanced_group)
        return wrapper

    def _build_preview(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.addWidget(QLabel("Preview:"))

        self.preview_label = QLabel("Select an input folder to see a preview.")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet("color: gray; border: 1px solid #ccc;")
        self.preview_label.setMinimumSize(500, 500)
        layout.addWidget(self.preview_label, stretch=1)

        self.preview_status_label = QLabel("")
        layout.addWidget(self.preview_status_label)
        return panel

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_preview()

    # ------------------------------------------------------------- logging
    def _log(self, message):
        self.log_view.appendPlainText(message)

    def _show_error(self, message, details=None):
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle("SegMetric.Scale — Error")
        box.setText(message)
        if details:
            box.setDetailedText(details)
        box.exec()

    # -------------------------------------------------------------- state
    def _current_settings(self) -> ScaleSettings:
        return ScaleSettings(
            marker_spacing_mm=self.spacing_spin.value(),
            adaptive_thresh_constant=self.thresh_constant_spin.value(),
            adaptive_thresh_win_size_min=self.win_min_spin.value(),
            adaptive_thresh_win_size_max=self.win_max_spin.value(),
            adaptive_thresh_win_size_step=self.win_step_spin.value(),
            prepare_win_size_max=self.prepare_win_max_spin.value(),
            prepare_win_size_step=self.prepare_win_step_spin.value(),
            prepare_error_correction_rate=self.prepare_error_correction_spin.value(),
            prepare_perspective_remove_pixel_per_cell=self.prepare_perspective_spin.value(),
            use_blob_fallback=self.blob_fallback_checkbox.isChecked(),
            blob_min_aspect=self.blob_min_aspect_spin.value(),
            blob_max_aspect=self.blob_max_aspect_spin.value(),
            prepare_blob_min_area=self.prepare_blob_min_area_spin.value(),
            prepare_blob_max_area=self.prepare_blob_max_area_spin.value(),
            final_blob_min_area=self.final_blob_min_area_spin.value(),
            final_blob_max_area=self.final_blob_max_area_spin.value(),
            crop_v_anchor=self._current_crop_v_anchor(),
            crop_v_size_pct=self.crop_v_size_spin.value(),
            crop_h_anchor=self._current_crop_h_anchor(),
            crop_h_size_pct=self.crop_h_size_spin.value(),
        )

    def _apply_settings_to_controls(self, settings: ScaleSettings):
        self.spacing_spin.setValue(settings.marker_spacing_mm)
        self.thresh_constant_spin.setValue(settings.adaptive_thresh_constant)
        self.win_min_spin.setValue(settings.adaptive_thresh_win_size_min)
        self.win_max_spin.setValue(settings.adaptive_thresh_win_size_max)
        self.win_step_spin.setValue(settings.adaptive_thresh_win_size_step)
        self.prepare_win_max_spin.setValue(settings.prepare_win_size_max)
        self.prepare_win_step_spin.setValue(settings.prepare_win_size_step)
        self.prepare_error_correction_spin.setValue(settings.prepare_error_correction_rate)
        self.prepare_perspective_spin.setValue(settings.prepare_perspective_remove_pixel_per_cell)
        self.blob_fallback_checkbox.setChecked(settings.use_blob_fallback)
        self.blob_min_aspect_spin.setValue(settings.blob_min_aspect)
        self.blob_max_aspect_spin.setValue(settings.blob_max_aspect)
        self.prepare_blob_min_area_spin.setValue(settings.prepare_blob_min_area)
        self.prepare_blob_max_area_spin.setValue(settings.prepare_blob_max_area)
        self.final_blob_min_area_spin.setValue(settings.final_blob_min_area)
        self.final_blob_max_area_spin.setValue(settings.final_blob_max_area)
        self._set_crop_v_anchor(settings.crop_v_anchor)
        self.crop_v_size_spin.setValue(settings.crop_v_size_pct)
        self._set_crop_h_anchor(settings.crop_h_anchor)
        self.crop_h_size_spin.setValue(settings.crop_h_size_pct)
        # If the loaded preset customized the thresholds, reveal them rather
        # than hiding an active customization behind the collapsed checkbox.
        customized = (
            settings.adaptive_thresh_constant != DEFAULTS.adaptive_thresh_constant
            or settings.adaptive_thresh_win_size_min != DEFAULTS.adaptive_thresh_win_size_min
            or settings.adaptive_thresh_win_size_max != DEFAULTS.adaptive_thresh_win_size_max
            or settings.adaptive_thresh_win_size_step != DEFAULTS.adaptive_thresh_win_size_step
            or settings.prepare_win_size_max != DEFAULTS.prepare_win_size_max
            or settings.prepare_win_size_step != DEFAULTS.prepare_win_size_step
            or settings.prepare_error_correction_rate != DEFAULTS.prepare_error_correction_rate
            or settings.prepare_perspective_remove_pixel_per_cell
            != DEFAULTS.prepare_perspective_remove_pixel_per_cell
        )
        self.threshold_checkbox.setChecked(customized)

        blob_customized = (
            settings.blob_min_aspect != DEFAULTS.blob_min_aspect
            or settings.blob_max_aspect != DEFAULTS.blob_max_aspect
            or settings.prepare_blob_min_area != DEFAULTS.prepare_blob_min_area
            or settings.prepare_blob_max_area != DEFAULTS.prepare_blob_max_area
            or settings.final_blob_min_area != DEFAULTS.final_blob_min_area
            or settings.final_blob_max_area != DEFAULTS.final_blob_max_area
        )
        self.blob_advanced_checkbox.setChecked(blob_customized)

    def _current_output_format(self):
        return "png" if self.png_radio.isChecked() else "tiff"

    def _is_ready(self):
        if not (self.input_folder and self.output_folder and self.first_input_file):
            return False
        if self.no_markers_radio.isChecked():
            return self._manual_scale_ready() and self._manual_crop_ready()
        return True

    def _input_file_names(self):
        try:
            return [os.path.basename(p) for p in find_input_files(self.input_folder)]
        except SegMetricError:
            return []

    def _manual_scale_ready(self):
        names = self._input_file_names()
        return bool(names) and all(name in self._manual_scale_by_name for name in names)

    def _manual_crop_ready(self):
        if self.no_crop_radio.isChecked():
            return True
        if self._manual_crop_bbox_by_name is None:
            return False
        names = self._input_file_names()
        return bool(names) and all(name in self._manual_crop_bbox_by_name for name in names)

    def _effective_crop_bbox_by_name(self):
        """None means "no cropping" -- driven by the crop-mode radio itself
        (not just whatever _manual_crop_bbox_by_name happens to hold), so
        switching back to "No crop" after configuring a region never
        accidentally reapplies the stale configuration.
        """
        if self.no_crop_radio.isChecked():
            return None
        return self._manual_crop_bbox_by_name

    def _update_run_button_state(self):
        self.run_btn.setEnabled(self._is_ready())

    def _set_controls_enabled(self, enabled):
        self.run_btn.setEnabled(bool(enabled and self._is_ready()))
        self.markers_present_radio.setEnabled(enabled)
        self.no_markers_radio.setEnabled(enabled)
        self.tiff_radio.setEnabled(enabled)
        self.png_radio.setEnabled(enabled)
        self.spacing_spin.setEnabled(enabled)
        self.blob_fallback_checkbox.setEnabled(enabled)
        self.threshold_checkbox.setEnabled(enabled)
        self.threshold_group.setEnabled(bool(enabled and self.threshold_checkbox.isChecked()))
        self.blob_advanced_checkbox.setEnabled(enabled)
        self.blob_advanced_group.setEnabled(bool(enabled and self.blob_advanced_checkbox.isChecked()))
        self.save_preset_btn.setEnabled(enabled)
        self.load_preset_btn.setEnabled(enabled)
        self.manual_group.setEnabled(enabled)
        self.crop_region_group.setEnabled(enabled)

    # --------------------------------------------------------- marker mode
    def _on_marker_mode_changed(self, _checked):
        no_markers = self.no_markers_radio.isChecked()
        self.scale_group.setVisible(not no_markers)
        self.crop_region_group.setVisible(not no_markers)
        self.threshold_wrapper.setVisible(not no_markers)
        self.blob_wrapper.setVisible(not no_markers)
        self.manual_group.setVisible(no_markers)
        self._update_preview()
        self._update_run_button_state()

    def _on_scale_mode_changed(self, _checked):
        self._manual_scale_by_name = {}
        self._manual_scale_source_by_name = {}
        self.scale_status_label.setText("⚠ No scale set yet.")
        self.scale_status_label.setStyleSheet("color: #b06a00;")
        self._update_run_button_state()

    def _on_crop_mode_changed(self, _checked):
        self._manual_crop_bbox_by_name = None
        self.set_crop_btn.setEnabled(not self.no_crop_radio.isChecked())
        if self.no_crop_radio.isChecked():
            self.crop_status_label.setText("No crop -- images are saved at full size.")
            self.crop_status_label.setStyleSheet("color: gray;")
        else:
            self.crop_status_label.setText("⚠ No crop region set yet.")
            self.crop_status_label.setStyleSheet("color: #b06a00;")
        self._update_run_button_state()

    def on_set_scale(self):
        if not self.input_folder:
            self._show_error("Choose an input folder first.")
            return
        files = find_input_files(self.input_folder)
        if not files:
            self._show_error("No input files found.")
            return

        if self.scale_batch_radio.isChecked():
            try:
                image = load_preview_image(files[0])
            except SegMetricError as exc:
                self._show_error(str(exc))
                return
            dialog = SetScaleDialog(image, os.path.basename(files[0]), parent=self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            scale = dialog.result_scale
            self._manual_scale_by_name = {os.path.basename(p): scale for p in files}
            self._manual_scale_source_by_name = {
                os.path.basename(p): SCALE_SOURCE_MANUAL_BATCH for p in files
            }
            self.scale_status_label.setText(
                f"✓ {scale:.6f} mm/pixel, applied to {len(files)} image(s)."
            )
        else:
            dialog = ScaleReviewDialog(files, parent=self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            self._manual_scale_by_name = dialog.results
            self._manual_scale_source_by_name = {
                name: SCALE_SOURCE_MANUAL for name in dialog.results
            }
            self.scale_status_label.setText(
                f"✓ Scale set individually for {len(dialog.results)} of {len(files)} image(s)."
            )
        self.scale_status_label.setStyleSheet("color: #006600;")
        self._update_run_button_state()

    def on_set_crop(self):
        if not self.input_folder:
            self._show_error("Choose an input folder first.")
            return
        files = find_input_files(self.input_folder)
        if not files:
            self._show_error("No input files found.")
            return

        if self.crop_batch_radio.isChecked():
            try:
                image = load_preview_image(files[0])
            except SegMetricError as exc:
                self._show_error(str(exc))
                return
            dialog = SetCropDialog(image, os.path.basename(files[0]), parent=self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            bbox = dialog.result_bbox
            self._manual_crop_bbox_by_name = {os.path.basename(p): bbox for p in files}
            self.crop_status_label.setText(f"✓ One region applied to {len(files)} image(s).")
        else:
            dialog = CropReviewDialog(files, parent=self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            self._manual_crop_bbox_by_name = dialog.results
            self.crop_status_label.setText(
                f"✓ Region set individually for {len(dialog.results)} of {len(files)} image(s)."
            )
        self.crop_status_label.setStyleSheet("color: #006600;")
        self._update_run_button_state()

    # -------------------------------------------------------- folder pick
    def on_browse_input(self):
        folder = QFileDialog.getExistingDirectory(self, "Select input folder")
        if not folder:
            return

        try:
            files = find_input_files(folder)
        except SegMetricError as exc:
            self._show_error(str(exc))
            self.input_folder = None
            self.first_input_file = None
            self.input_line.clear()
            self._update_run_button_state()
            return

        self.input_folder = folder
        self.input_line.setText(folder)
        self.first_input_file = files[0]

        # A new input folder invalidates any manual scale/crop already
        # configured against the old one's file list.
        self._manual_scale_by_name = {}
        self._manual_scale_source_by_name = {}
        self._manual_crop_bbox_by_name = None
        self.scale_status_label.setText("⚠ No scale set yet.")
        self.scale_status_label.setStyleSheet("color: #b06a00;")
        if not self.no_crop_radio.isChecked():
            self.crop_status_label.setText("⚠ No crop region set yet.")
            self.crop_status_label.setStyleSheet("color: #b06a00;")

        self._log(f"Found {len(files)} file(s) in {folder}.")
        self._log(f"Previewing: {os.path.basename(files[0])}")

        try:
            self.preview_image_bgr = load_preview_image(self.first_input_file)
        except SegMetricError as exc:
            self._show_error(str(exc))
            self.preview_image_bgr = None

        self._update_preview()
        self._update_run_button_state()

    def on_browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Select output folder")
        if not folder:
            return
        self.output_folder = folder
        self.output_line.setText(folder)
        self._update_run_button_state()

    # ------------------------------------------------------------- preview
    def _update_preview(self):
        if self.preview_image_bgr is None:
            return

        if self.no_markers_radio.isChecked():
            # No marker detection to preview in this mode -- just show the
            # plain image; "Set Scale…"/"Set Crop Region…" open their own
            # interactive canvases.
            pixmap = bgr_to_qpixmap(self.preview_image_bgr)
            status_text = "No-markers mode -- use \"Set Scale…\" / \"Set Crop Region…\" below."
        else:
            pixmap, status_text = render_marker_preview(self.preview_image_bgr, self._current_settings())
        scaled = pixmap.scaled(
            self.preview_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setPixmap(scaled)
        self.preview_status_label.setText(status_text)

    def on_settings_changed(self):
        self._update_preview()

    def on_threshold_toggle(self, checked):
        self.threshold_group.setEnabled(checked)
        self._update_preview()

    def on_blob_advanced_toggle(self, checked):
        self.blob_advanced_group.setEnabled(checked)
        self._update_preview()

    # ------------------------------------------------------------ presets
    def on_save_preset(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save preset", "scale_preset.json", "JSON files (*.json)"
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"

        try:
            save_scale_preset(path, self._current_settings())
        except SegMetricError as exc:
            self._show_error(str(exc))
            return

        self._log(f"Preset saved to {path}")

    def on_load_preset(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load preset", "", "JSON files (*.json)"
        )
        if not path:
            return

        try:
            settings = load_scale_preset(path)
        except SegMetricError as exc:
            self._show_error(str(exc))
            return

        self._apply_settings_to_controls(settings)
        self._update_preview()
        self._log(f"Preset loaded from {path}")

    # ------------------------------------------------------------------ run
    def on_run(self):
        self._set_controls_enabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        self._log("Starting run…")

        if self.no_markers_radio.isChecked():
            self.scale_worker = ManualScaleJobWorker(
                self.input_folder,
                self.output_folder,
                dict(self._manual_scale_by_name),
                dict(self._manual_scale_source_by_name),
                self._effective_crop_bbox_by_name(),
                output_format=self._current_output_format(),
            )
        else:
            self.scale_worker = ScaleJobWorker(
                self.input_folder,
                self.output_folder,
                self._current_settings(),
                output_format=self._current_output_format(),
            )
        self.scale_worker.progress.connect(self.on_job_progress)
        self.scale_worker.error.connect(self.on_job_error)
        self.scale_worker.finished_ok.connect(self.on_job_finished)
        self.scale_worker.start()

    def on_stop(self):
        if self.scale_worker is not None and self.scale_worker.isRunning():
            self.scale_worker.requestInterruption()
            self.stop_btn.setEnabled(False)
            self._log("Stopping… finishing the current file first.")

    def on_job_progress(self, fraction, message):
        self.progress_bar.setValue(int(fraction * 100))
        self._log(message)

    def on_job_error(self, message):
        self._set_controls_enabled(True)
        self.stop_btn.setEnabled(False)
        details = (
            None
            if self.no_markers_radio.isChecked()
            else "See segmetric_scale.log inside the output folder's 'scale' directory for technical details."
        )
        self._show_error(message, details=details)
        self._log(f"ERROR: {message}")

    def on_job_finished(self, result):
        self._set_controls_enabled(True)
        self.stop_btn.setEnabled(False)

        verb = "Stopped" if result.interrupted else "Done"
        summary = (
            f"{verb} — {result.panels_cropped} image(s) cropped, "
            f"scales for {len(result.scale_rows)} file(s) saved to {result.output_dir}."
        )
        flagged = sum(1 for _, _, source in result.scale_rows if source == "batch_median")
        if flagged:
            summary += f"\n{flagged} file(s) used the batch-median fallback scale (flagged in scales.csv)."
        if result.files_skipped:
            summary += f"\n{len(result.files_skipped)} file(s) were skipped — see status log."
            for fname, reason in result.files_skipped:
                self._log(f"Skipped {fname}: {reason}")

        self._log(summary)
        title = "SegMetric.Scale — Stopped" if result.interrupted else "SegMetric.Scale — Run complete"
        QMessageBox.information(self, title, summary)
