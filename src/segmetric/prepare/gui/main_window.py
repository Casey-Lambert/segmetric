import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
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
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from segmetric.errors import SegMetricError
from segmetric.scale.core.model import ScaleSettings
from segmetric.scale.core.presets import load_scale_preset, save_scale_preset
from segmetric.set.core.presets import load_preset as load_metadata_preset
from segmetric.tag.core.discovery import find_input_files
from segmetric.tag.core.naming import OcrRegion

from ..core.metadata import preset_column_order
from .preview import load_preview_page, render_grid_preview
from .worker import PrepareJobWorker

MIN_GRID = 1
MAX_GRID = 8
DEFAULT_GRID = 4
SCALE_DEFAULTS = ScaleSettings()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SegMetric.Prepare — Tag + Set + Scale")
        self.resize(1320, 840)

        self.input_folder = None
        self.output_folder = None
        self.first_input_file = None
        self.preview_page_bgr = None
        self.loaded_preset = None  # segmetric.set Preset, optional

        self.prepare_worker = None

        self._build_ui()
        self._update_run_button_state()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_controls())
        splitter.addWidget(self._build_preview())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(splitter)

    def _build_controls(self):
        content = QWidget()
        layout = QVBoxLayout(content)

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

        output_hint = QLabel(
            ""
        )
        output_hint.setStyleSheet("color: gray;")
        output_hint.setWordWrap(True)
        folders_layout.addRow("", output_hint)

        layout.addWidget(folders_group)

        # -- tabs --
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_panels_tab(), "Panels")
        self.tabs.addTab(self._build_metadata_tab(), "Metadata")
        self.tabs.addTab(self._build_scale_tab(), "Scale")
        layout.addWidget(self.tabs)

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

        content.setMinimumWidth(460)
        content.setMaximumWidth(560)
        return content

    @staticmethod
    def _scrollable(widget):
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setWidget(widget)
        return scroll_area

    # --------------------------------------------------------- Panels tab
    def _build_panels_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        format_group = QGroupBox("Output format")
        format_layout = QHBoxLayout(format_group)
        self.tiff_radio = QRadioButton("TIFF (recommended)")
        self.tiff_radio.setChecked(True)
        self.png_radio = QRadioButton("PNG")
        self.jpeg_radio = QRadioButton("JPEG")
        self.output_format_group = QButtonGroup(format_group)
        self.output_format_group.addButton(self.tiff_radio)
        self.output_format_group.addButton(self.png_radio)
        self.output_format_group.addButton(self.jpeg_radio)
        format_layout.addWidget(self.tiff_radio)
        format_layout.addWidget(self.png_radio)
        format_layout.addWidget(self.jpeg_radio)
        layout.addWidget(format_group)

        grid_group = QGroupBox("Grid")
        grid_layout = QFormLayout(grid_group)

        self.rows_spin = QSpinBox()
        self.rows_spin.setRange(MIN_GRID, MAX_GRID)
        self.rows_spin.setValue(DEFAULT_GRID)
        self.rows_spin.valueChanged.connect(self.on_grid_params_changed)
        grid_layout.addRow("Rows:", self.rows_spin)

        self.cols_spin = QSpinBox()
        self.cols_spin.setRange(MIN_GRID, MAX_GRID)
        self.cols_spin.setValue(DEFAULT_GRID)
        self.cols_spin.valueChanged.connect(self.on_grid_params_changed)
        grid_layout.addRow("Columns:", self.cols_spin)
        layout.addWidget(grid_group)

        naming_group = QGroupBox("Naming")
        naming_layout = QVBoxLayout(naming_group)

        self.cv_checkbox = QCheckBox("Name panels with computer vision (OCR)")
        self.cv_checkbox.toggled.connect(self.on_cv_toggle)
        naming_layout.addWidget(self.cv_checkbox)

        naming_layout.addWidget(self._build_ocr_region_controls())
        naming_layout.addWidget(self._build_ocr_engine_controls())
        layout.addWidget(naming_group)

        layout.addStretch(1)
        return self._scrollable(tab)

    def _build_ocr_engine_controls(self):
        self.engine_group = QGroupBox("OCR engine")
        self.engine_group.setEnabled(False)
        engine_layout = QVBoxLayout(self.engine_group)

        self.gpu_radio = QRadioButton("GPU (recommended)")
        self.gpu_radio.setChecked(True)
        self.cpu_radio = QRadioButton("CPU")
        self.engine_button_group = QButtonGroup(self.engine_group)
        self.engine_button_group.addButton(self.gpu_radio)
        self.engine_button_group.addButton(self.cpu_radio)

        engine_row = QHBoxLayout()
        engine_row.addWidget(self.gpu_radio)
        engine_row.addWidget(self.cpu_radio)
        engine_layout.addLayout(engine_row)

        self.engine_warning = QLabel(
            "CPU is much slower than GPU — expect long processing times, "
            "especially with larger batches."
        )
        self.engine_warning.setStyleSheet("color: #b06a00;")
        self.engine_warning.setWordWrap(True)
        self.engine_warning.setVisible(False)
        engine_layout.addWidget(self.engine_warning)

        self.cpu_radio.toggled.connect(self.engine_warning.setVisible)

        return self.engine_group

    def _build_ocr_region_controls(self):
        self.region_group = QGroupBox("OCR search region")
        self.region_group.setEnabled(False)
        region_layout = QFormLayout(self.region_group)

        self.v_top_radio = QRadioButton("Top")
        self.v_bottom_radio = QRadioButton("Bottom")
        self.v_bottom_radio.setChecked(True)
        self.v_anchor_group = QButtonGroup(self.region_group)
        self.v_anchor_group.addButton(self.v_top_radio)
        self.v_anchor_group.addButton(self.v_bottom_radio)
        self.v_top_radio.toggled.connect(self.on_ocr_region_changed)
        v_anchor_row = QHBoxLayout()
        v_anchor_row.addWidget(self.v_top_radio)
        v_anchor_row.addWidget(self.v_bottom_radio)
        region_layout.addRow("From:", v_anchor_row)

        self.v_size_spin = QSpinBox()
        self.v_size_spin.setRange(1, 100)
        self.v_size_spin.setValue(50)
        self.v_size_spin.setSuffix("%")
        self.v_size_spin.valueChanged.connect(self.on_ocr_region_changed)
        region_layout.addRow("Vertical:", self.v_size_spin)

        self.h_left_radio = QRadioButton("Left")
        self.h_left_radio.setChecked(True)
        self.h_right_radio = QRadioButton("Right")
        self.h_anchor_group = QButtonGroup(self.region_group)
        self.h_anchor_group.addButton(self.h_left_radio)
        self.h_anchor_group.addButton(self.h_right_radio)
        self.h_left_radio.toggled.connect(self.on_ocr_region_changed)
        h_anchor_row = QHBoxLayout()
        h_anchor_row.addWidget(self.h_left_radio)
        h_anchor_row.addWidget(self.h_right_radio)
        region_layout.addRow("From:", h_anchor_row)

        self.h_size_spin = QSpinBox()
        self.h_size_spin.setRange(1, 100)
        self.h_size_spin.setValue(100)
        self.h_size_spin.setSuffix("%")
        self.h_size_spin.valueChanged.connect(self.on_ocr_region_changed)
        region_layout.addRow("Horizontal", self.h_size_spin)

        return self.region_group

    # ------------------------------------------------------- Metadata tab
    def _build_metadata_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        hint = QLabel(
            "Optional. Load a preset built in segmetric-set to pull "
            "metadata columns from the filename into "
            "summary.csv"
        )
        hint.setStyleSheet("color: gray;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        button_row = QHBoxLayout()
        self.load_metadata_preset_btn = QPushButton("Load Preset…")
        self.load_metadata_preset_btn.clicked.connect(self.on_load_metadata_preset)
        self.clear_metadata_preset_btn = QPushButton("Clear")
        self.clear_metadata_preset_btn.clicked.connect(self.on_clear_metadata_preset)
        button_row.addWidget(self.load_metadata_preset_btn)
        button_row.addWidget(self.clear_metadata_preset_btn)
        layout.addLayout(button_row)

        self.metadata_preset_label = QLabel(
            "No preset loaded"
            
        )
        self.metadata_preset_label.setWordWrap(True)
        layout.addWidget(self.metadata_preset_label)

        self.metadata_warning_label = QLabel(
            "Computer-vision naming is off (see 'Panels'tab)"
        )
        self.metadata_warning_label.setStyleSheet("color: #b06a00;")
        self.metadata_warning_label.setWordWrap(True)
        self.metadata_warning_label.setVisible(False)
        layout.addWidget(self.metadata_warning_label)

        layout.addStretch(1)
        return self._scrollable(tab)

    # ----------------------------------------------------------- Scale tab
    def _build_scale_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        crop_format_group = QGroupBox("Output image format")
        crop_format_layout = QHBoxLayout(crop_format_group)
        self.crop_tiff_radio = QRadioButton("TIFF (recommended)")
        self.crop_tiff_radio.setChecked(True)
        self.crop_png_radio = QRadioButton("PNG")
        self.crop_output_format_group = QButtonGroup(crop_format_group)
        self.crop_output_format_group.addButton(self.crop_tiff_radio)
        self.crop_output_format_group.addButton(self.crop_png_radio)
        crop_format_layout.addWidget(self.crop_tiff_radio)
        crop_format_layout.addWidget(self.crop_png_radio)
        layout.addWidget(crop_format_group)

        scale_group = QGroupBox("Scale")
        scale_layout = QFormLayout(scale_group)

        self.spacing_spin = QDoubleSpinBox()
        self.spacing_spin.setRange(0.01, 1000.0)
        self.spacing_spin.setDecimals(3)
        self.spacing_spin.setSuffix(" mm")
        self.spacing_spin.setValue(SCALE_DEFAULTS.marker_spacing_mm)
        self.spacing_spin.valueChanged.connect(self.on_scale_settings_changed)
        scale_layout.addRow("Marker spacing:", self.spacing_spin)

        spacing_hint = QLabel(
            "Distance between ArUco marker centers"
        )
        spacing_hint.setStyleSheet("color: gray;")
        spacing_hint.setWordWrap(True)
        scale_layout.addRow("", spacing_hint)

        self.blob_fallback_checkbox = QCheckBox("Use blob-detection fallback")
        self.blob_fallback_checkbox.setChecked(SCALE_DEFAULTS.use_blob_fallback)
        self.blob_fallback_checkbox.toggled.connect(self.on_scale_settings_changed)
        scale_layout.addRow("", self.blob_fallback_checkbox)

        blob_hint = QLabel(
            "If ArUco decoding finds fewer than 4 markers, use plain shape detection"
        )
        blob_hint.setStyleSheet("color: gray;")
        blob_hint.setWordWrap(True)
        scale_layout.addRow("", blob_hint)

        layout.addWidget(scale_group)

        layout.addWidget(self._build_threshold_controls())
        layout.addWidget(self._build_blob_controls())

        preset_row = QHBoxLayout()
        self.save_scale_preset_btn = QPushButton("Save Scale Preset")
        self.save_scale_preset_btn.clicked.connect(self.on_save_scale_preset)
        self.load_scale_preset_btn = QPushButton("Load Scale Preset")
        self.load_scale_preset_btn.clicked.connect(self.on_load_scale_preset)
        preset_row.addWidget(self.save_scale_preset_btn)
        preset_row.addWidget(self.load_scale_preset_btn)
        layout.addLayout(preset_row)

        layout.addStretch(1)
        return self._scrollable(tab)

    def _build_threshold_controls(self):
        self.threshold_checkbox = QCheckBox("Customize ArCuo detection threshold")
        self.threshold_checkbox.toggled.connect(self.on_threshold_toggle)

        self.threshold_group = QGroupBox()
        self.threshold_group.setEnabled(False)
        threshold_layout = QFormLayout(self.threshold_group)

        self.thresh_constant_spin = QSpinBox()
        self.thresh_constant_spin.setRange(1, 100)
        self.thresh_constant_spin.setValue(SCALE_DEFAULTS.adaptive_thresh_constant)
        self.thresh_constant_spin.valueChanged.connect(self.on_scale_settings_changed)
        threshold_layout.addRow("Adaptive thresh constant:", self.thresh_constant_spin)

        self.win_min_spin = QSpinBox()
        self.win_min_spin.setRange(1, 999)
        self.win_min_spin.setValue(SCALE_DEFAULTS.adaptive_thresh_win_size_min)
        self.win_min_spin.valueChanged.connect(self.on_scale_settings_changed)
        threshold_layout.addRow("Win size min:", self.win_min_spin)

        threshold_layout.addRow(QLabel("<b>Prepare pass</b> (raw panel, before crop):"))

        self.prepare_win_max_spin = QSpinBox()
        self.prepare_win_max_spin.setRange(1, 999)
        self.prepare_win_max_spin.setValue(SCALE_DEFAULTS.prepare_win_size_max)
        self.prepare_win_max_spin.valueChanged.connect(self.on_scale_settings_changed)
        threshold_layout.addRow("Win size max:", self.prepare_win_max_spin)

        self.prepare_win_step_spin = QSpinBox()
        self.prepare_win_step_spin.setRange(1, 999)
        self.prepare_win_step_spin.setValue(SCALE_DEFAULTS.prepare_win_size_step)
        self.prepare_win_step_spin.valueChanged.connect(self.on_scale_settings_changed)
        threshold_layout.addRow("Win size step:", self.prepare_win_step_spin)

        self.prepare_error_correction_spin = QDoubleSpinBox()
        self.prepare_error_correction_spin.setRange(0.0, 1.0)
        self.prepare_error_correction_spin.setDecimals(2)
        self.prepare_error_correction_spin.setSingleStep(0.05)
        self.prepare_error_correction_spin.setValue(SCALE_DEFAULTS.prepare_error_correction_rate)
        self.prepare_error_correction_spin.valueChanged.connect(self.on_scale_settings_changed)
        threshold_layout.addRow("Error correction rate:", self.prepare_error_correction_spin)

        self.prepare_perspective_spin = QSpinBox()
        self.prepare_perspective_spin.setRange(1, 999)
        self.prepare_perspective_spin.setValue(
            SCALE_DEFAULTS.prepare_perspective_remove_pixel_per_cell
        )
        self.prepare_perspective_spin.valueChanged.connect(self.on_scale_settings_changed)
        threshold_layout.addRow("Perspective remove px/cell:", self.prepare_perspective_spin)

        threshold_layout.addRow(QLabel("<b>Final pass</b> (after crop + upscale):"))

        self.win_max_spin = QSpinBox()
        self.win_max_spin.setRange(1, 999)
        self.win_max_spin.setValue(SCALE_DEFAULTS.adaptive_thresh_win_size_max)
        self.win_max_spin.valueChanged.connect(self.on_scale_settings_changed)
        threshold_layout.addRow("Win size max:", self.win_max_spin)

        self.win_step_spin = QSpinBox()
        self.win_step_spin.setRange(1, 999)
        self.win_step_spin.setValue(SCALE_DEFAULTS.adaptive_thresh_win_size_step)
        self.win_step_spin.valueChanged.connect(self.on_scale_settings_changed)
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
        self.blob_min_aspect_spin.setValue(SCALE_DEFAULTS.blob_min_aspect)
        self.blob_min_aspect_spin.valueChanged.connect(self.on_scale_settings_changed)
        blob_layout.addRow("Min aspect ratio:", self.blob_min_aspect_spin)

        self.blob_max_aspect_spin = QDoubleSpinBox()
        self.blob_max_aspect_spin.setRange(0.01, 10.0)
        self.blob_max_aspect_spin.setDecimals(2)
        self.blob_max_aspect_spin.setSingleStep(0.05)
        self.blob_max_aspect_spin.setValue(SCALE_DEFAULTS.blob_max_aspect)
        self.blob_max_aspect_spin.valueChanged.connect(self.on_scale_settings_changed)
        blob_layout.addRow("Max aspect ratio:", self.blob_max_aspect_spin)

        blob_layout.addRow(QLabel("<b>Prepare pass</b> blob area (px²):"))

        self.prepare_blob_min_area_spin = QSpinBox()
        self.prepare_blob_min_area_spin.setRange(1, 100_000_000)
        self.prepare_blob_min_area_spin.setValue(SCALE_DEFAULTS.prepare_blob_min_area)
        self.prepare_blob_min_area_spin.valueChanged.connect(self.on_scale_settings_changed)
        blob_layout.addRow("Min area:", self.prepare_blob_min_area_spin)

        self.prepare_blob_max_area_spin = QSpinBox()
        self.prepare_blob_max_area_spin.setRange(1, 100_000_000)
        self.prepare_blob_max_area_spin.setValue(SCALE_DEFAULTS.prepare_blob_max_area)
        self.prepare_blob_max_area_spin.valueChanged.connect(self.on_scale_settings_changed)
        blob_layout.addRow("Max area:", self.prepare_blob_max_area_spin)

        blob_layout.addRow(QLabel("<b>Final pass</b> blob area (px²):"))

        self.final_blob_min_area_spin = QSpinBox()
        self.final_blob_min_area_spin.setRange(1, 100_000_000)
        self.final_blob_min_area_spin.setValue(SCALE_DEFAULTS.final_blob_min_area)
        self.final_blob_min_area_spin.valueChanged.connect(self.on_scale_settings_changed)
        blob_layout.addRow("Min area:", self.final_blob_min_area_spin)

        self.final_blob_max_area_spin = QSpinBox()
        self.final_blob_max_area_spin.setRange(1, 100_000_000)
        self.final_blob_max_area_spin.setValue(SCALE_DEFAULTS.final_blob_max_area)
        self.final_blob_max_area_spin.valueChanged.connect(self.on_scale_settings_changed)
        blob_layout.addRow("Max area:", self.final_blob_max_area_spin)

        wrapper = QWidget()
        wrapper_layout = QVBoxLayout(wrapper)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.addWidget(self.blob_advanced_checkbox)
        wrapper_layout.addWidget(self.blob_advanced_group)
        return wrapper

    # -------------------------------------------------------------- preview
    def _build_preview(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)

        layout.addWidget(QLabel("Preview:"))
        self.grid_preview_label = QLabel("Select an input folder to see a preview.")
        self.grid_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.grid_preview_label.setStyleSheet("color: gray; border: 1px solid #ccc;")
        self.grid_preview_label.setMinimumSize(480, 300)
        layout.addWidget(self.grid_preview_label, stretch=1)

        return self._scrollable(panel)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_preview()

    # ------------------------------------------------------------- logging
    def _log(self, message):
        self.log_view.appendPlainText(message)

    def _show_error(self, message, details=None):
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle("SegMetric.Prepare — Error")
        box.setText(message)
        if details:
            box.setDetailedText(details)
        box.exec()

    # -------------------------------------------------------------- state
    def _current_ocr_region(self):
        return OcrRegion(
            v_anchor="top" if self.v_top_radio.isChecked() else "bottom",
            v_size_pct=self.v_size_spin.value(),
            h_anchor="left" if self.h_left_radio.isChecked() else "right",
            h_size_pct=self.h_size_spin.value(),
        )

    def _current_gpu_choice(self):
        return self.gpu_radio.isChecked()

    def _current_output_format(self):
        if self.png_radio.isChecked():
            return "png"
        if self.jpeg_radio.isChecked():
            return "jpeg"
        return "tiff"

    def _current_crop_output_format(self):
        return "png" if self.crop_png_radio.isChecked() else "tiff"

    def _current_scale_settings(self) -> ScaleSettings:
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
        )

    def _apply_scale_settings_to_controls(self, settings: ScaleSettings):
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
        customized = (
            settings.adaptive_thresh_constant != SCALE_DEFAULTS.adaptive_thresh_constant
            or settings.adaptive_thresh_win_size_min != SCALE_DEFAULTS.adaptive_thresh_win_size_min
            or settings.adaptive_thresh_win_size_max != SCALE_DEFAULTS.adaptive_thresh_win_size_max
            or settings.adaptive_thresh_win_size_step != SCALE_DEFAULTS.adaptive_thresh_win_size_step
            or settings.prepare_win_size_max != SCALE_DEFAULTS.prepare_win_size_max
            or settings.prepare_win_size_step != SCALE_DEFAULTS.prepare_win_size_step
            or settings.prepare_error_correction_rate != SCALE_DEFAULTS.prepare_error_correction_rate
            or settings.prepare_perspective_remove_pixel_per_cell
            != SCALE_DEFAULTS.prepare_perspective_remove_pixel_per_cell
        )
        self.threshold_checkbox.setChecked(customized)

        blob_customized = (
            settings.blob_min_aspect != SCALE_DEFAULTS.blob_min_aspect
            or settings.blob_max_aspect != SCALE_DEFAULTS.blob_max_aspect
            or settings.prepare_blob_min_area != SCALE_DEFAULTS.prepare_blob_min_area
            or settings.prepare_blob_max_area != SCALE_DEFAULTS.prepare_blob_max_area
            or settings.final_blob_min_area != SCALE_DEFAULTS.final_blob_min_area
            or settings.final_blob_max_area != SCALE_DEFAULTS.final_blob_max_area
        )
        self.blob_advanced_checkbox.setChecked(blob_customized)

    def _is_ready(self):
        return bool(self.input_folder) and bool(self.output_folder) and bool(self.first_input_file)

    def _update_run_button_state(self):
        self.run_btn.setEnabled(self._is_ready())

    def _set_controls_enabled(self, enabled):
        self.run_btn.setEnabled(bool(enabled and self._is_ready()))
        self.rows_spin.setEnabled(enabled)
        self.cols_spin.setEnabled(enabled)
        self.cv_checkbox.setEnabled(enabled)
        self.tiff_radio.setEnabled(enabled)
        self.png_radio.setEnabled(enabled)
        self.jpeg_radio.setEnabled(enabled)
        self.region_group.setEnabled(bool(enabled and self.cv_checkbox.isChecked()))
        self.engine_group.setEnabled(bool(enabled and self.cv_checkbox.isChecked()))
        self.crop_tiff_radio.setEnabled(enabled)
        self.crop_png_radio.setEnabled(enabled)
        self.spacing_spin.setEnabled(enabled)
        self.blob_fallback_checkbox.setEnabled(enabled)
        self.threshold_checkbox.setEnabled(enabled)
        self.threshold_group.setEnabled(bool(enabled and self.threshold_checkbox.isChecked()))
        self.blob_advanced_checkbox.setEnabled(enabled)
        self.blob_advanced_group.setEnabled(bool(enabled and self.blob_advanced_checkbox.isChecked()))
        self.save_scale_preset_btn.setEnabled(enabled)
        self.load_scale_preset_btn.setEnabled(enabled)
        self.load_metadata_preset_btn.setEnabled(enabled)
        self.clear_metadata_preset_btn.setEnabled(enabled)

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

        self._log(f"Found {len(files)} file(s) in {folder}.")
        self._log(f"Previewing: {os.path.basename(files[0])}")

        try:
            self.preview_page_bgr = load_preview_page(self.first_input_file)
        except SegMetricError as exc:
            self._show_error(str(exc))
            self.preview_page_bgr = None

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
        if self.preview_page_bgr is None:
            return

        ocr_region = self._current_ocr_region() if self.cv_checkbox.isChecked() else None
        grid_pixmap = render_grid_preview(
            self.preview_page_bgr, self.rows_spin.value(), self.cols_spin.value(), ocr_region
        )

        scaled_grid = grid_pixmap.scaled(
            self.grid_preview_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.grid_preview_label.setPixmap(scaled_grid)

    def on_grid_params_changed(self):
        self._update_preview()

    def on_cv_toggle(self, checked):
        self.region_group.setEnabled(checked)
        self.engine_group.setEnabled(checked)
        self._update_metadata_warning()
        self._update_preview()

    def on_ocr_region_changed(self):
        self._update_preview()

    def on_threshold_toggle(self, checked):
        self.threshold_group.setEnabled(checked)

    def on_blob_advanced_toggle(self, checked):
        self.blob_advanced_group.setEnabled(checked)

    def on_scale_settings_changed(self):
        pass

    # ---------------------------------------------------- metadata preset
    def _update_metadata_warning(self):
        show = self.loaded_preset is not None and not self.cv_checkbox.isChecked()
        self.metadata_warning_label.setVisible(show)

    def on_load_metadata_preset(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load metadata preset", "", "JSON files (*.json)"
        )
        if not path:
            return

        try:
            preset = load_metadata_preset(path)
        except SegMetricError as exc:
            self._show_error(str(exc))
            return

        self.loaded_preset = preset
        columns = preset_column_order(preset)
        columns_text = ", ".join(columns) if columns else "(no columns included)"
        self.metadata_preset_label.setText(f"Loaded: {preset.name}\nColumns: {columns_text}")
        self._update_metadata_warning()
        self._log(f"Metadata preset loaded from {path}")

    def on_clear_metadata_preset(self):
        self.loaded_preset = None
        self.metadata_preset_label.setText(
            "No preset loaded — summary.csv will only have file_name, "
            "mm_per_pixel, scale_source."
        )
        self._update_metadata_warning()

    # -------------------------------------------------------- scale preset
    def on_save_scale_preset(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save scale preset", "scale_preset.json", "JSON files (*.json)"
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"

        try:
            save_scale_preset(path, self._current_scale_settings())
        except SegMetricError as exc:
            self._show_error(str(exc))
            return

        self._log(f"Scale preset saved to {path}")

    def on_load_scale_preset(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load scale preset", "", "JSON files (*.json)"
        )
        if not path:
            return

        try:
            settings = load_scale_preset(path)
        except SegMetricError as exc:
            self._show_error(str(exc))
            return

        self._apply_scale_settings_to_controls(settings)
        self._update_preview()
        self._log(f"Scale preset loaded from {path}")

    # ------------------------------------------------------------------ run
    def on_run(self):
        self._set_controls_enabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        self._log("Starting run…")

        self.prepare_worker = PrepareJobWorker(
            self.input_folder,
            self.output_folder,
            self.rows_spin.value(),
            self.cols_spin.value(),
            self.cv_checkbox.isChecked(),
            ocr_region=self._current_ocr_region(),
            gpu=self._current_gpu_choice(),
            output_format=self._current_output_format(),
            scale_settings=self._current_scale_settings(),
            preset=self.loaded_preset,
            crop_output_format=self._current_crop_output_format(),
        )
        self.prepare_worker.progress.connect(self.on_job_progress)
        self.prepare_worker.error.connect(self.on_job_error)
        self.prepare_worker.finished_ok.connect(self.on_job_finished)
        self.prepare_worker.start()

    def on_stop(self):
        if self.prepare_worker is not None and self.prepare_worker.isRunning():
            self.prepare_worker.requestInterruption()
            self.stop_btn.setEnabled(False)
            self._log("Stopping… finishing the current step first.")

    def on_job_progress(self, fraction, message):
        self.progress_bar.setValue(int(fraction * 100))
        self._log(message)

    def on_job_error(self, message):
        self._set_controls_enabled(True)
        self.stop_btn.setEnabled(False)
        self._show_error(
            message,
            details="See segmetric_tag.log in <output>/panels/ and "
            "segmetric_scale.log in <output>/scale/ for technical details.",
        )
        self._log(f"ERROR: {message}")

    def on_job_finished(self, result):
        self._set_controls_enabled(True)
        self.stop_btn.setEnabled(False)

        verb = "Stopped" if result.interrupted else "Done"
        summary = f"{verb} — {result.panels_saved} panel(s) saved, {result.panels_cropped} cropped."
        if result.summary_csv_path:
            summary += f"\nSummary saved to {result.summary_csv_path}."

        flagged = sum(1 for _, _, source in result.scale_rows if source == "batch_median")
        if flagged:
            summary += (
                f"\n{flagged} file(s) used the batch-median fallback scale "
                "(flagged in summary.csv)."
            )

        skipped_total = len(result.tag_files_skipped) + len(result.scale_files_skipped)
        if skipped_total:
            summary += f"\n{skipped_total} file(s) were skipped — see status log."
            for fname, reason in result.tag_files_skipped:
                self._log(f"Skipped (panel splitting) {fname}: {reason}")
            for fname, reason in result.scale_files_skipped:
                self._log(f"Skipped (scale) {fname}: {reason}")

        self._log(summary)
        title = "SegMetric.Prepare — Stopped" if result.interrupted else "SegMetric.Prepare — Run complete"
        QMessageBox.information(self, title, summary)
