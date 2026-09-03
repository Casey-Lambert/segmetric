import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
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
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..core.discovery import find_input_files
from ..core.errors import SegMetricError
from ..core.naming import OcrRegion
from .preview import load_preview_page, render_grid_preview
from .worker import SplitJobWorker

MIN_GRID = 1
MAX_GRID = 8
DEFAULT_GRID = 4


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SegMetric.Tag — Split and Name Panels")
        self.resize(1200, 760)

        self.input_folder = None
        self.output_folder = None
        self.first_input_file = None
        self.preview_image_bgr = None

        self.split_worker = None

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

        output_hint = QLabel(" ")
        output_hint.setStyleSheet("color: gray;")
        folders_layout.addRow("", output_hint)

        self.tiff_radio = QRadioButton("TIFF (recommended)")
        self.tiff_radio.setChecked(True)
        self.png_radio = QRadioButton("PNG")
        self.jpeg_radio = QRadioButton("JPEG")
        self.output_format_group = QButtonGroup(folders_group)
        self.output_format_group.addButton(self.tiff_radio)
        self.output_format_group.addButton(self.png_radio)
        self.output_format_group.addButton(self.jpeg_radio)
        format_row = QHBoxLayout()
        format_row.addWidget(self.tiff_radio)
        format_row.addWidget(self.png_radio)
        format_row.addWidget(self.jpeg_radio)
        folders_layout.addRow("Output format:", format_row)

        layout.addWidget(folders_group)

        # -- grid params --
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

        # -- naming --
        naming_group = QGroupBox("Naming")
        naming_layout = QVBoxLayout(naming_group)

        self.cv_checkbox = QCheckBox("Name panels with computer vision (OCR)")
        self.cv_checkbox.toggled.connect(self.on_cv_toggle)
        naming_layout.addWidget(self.cv_checkbox)

        naming_layout.addWidget(self._build_ocr_region_controls())
        naming_layout.addWidget(self._build_ocr_engine_controls())

        layout.addWidget(naming_group)

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

        panel.setMinimumWidth(420)
        panel.setMaximumWidth(520)
        return panel

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
            "especially with more panels."
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
        self.v_bottom_radio.setChecked(True)  # matches the notebook's bottom-half default
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
        self.h_left_radio.setChecked(True)  # matches the notebook's full-width default
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

    def _build_preview(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.addWidget(QLabel("Preview:"))

        self.preview_label = QLabel("Select an input folder to see a preview.")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setStyleSheet("color: gray; border: 1px solid #ccc;")
        self.preview_label.setMinimumSize(500, 500)
        layout.addWidget(self.preview_label, stretch=1)
        return panel

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_grid_preview()

    # ------------------------------------------------------------- logging
    def _log(self, message):
        self.log_view.appendPlainText(message)

    def _show_error(self, message, details=None):
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Critical)
        box.setWindowTitle("SegMetric.Tag — Error")
        box.setText(message)
        if details:
            box.setDetailedText(details)
        box.exec()

    # -------------------------------------------------------------- state
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

    def _is_ready(self):
        return bool(self.input_folder) and bool(self.output_folder) and bool(self.first_input_file)

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
            self.preview_image_bgr = load_preview_page(self.first_input_file)
        except SegMetricError as exc:
            self._show_error(str(exc))
            self.preview_image_bgr = None

        self._update_grid_preview()
        self._update_run_button_state()

    def on_browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Select output folder")
        if not folder:
            return
        self.output_folder = folder
        self.output_line.setText(folder)
        self._update_run_button_state()

    # ------------------------------------------------------------- preview
    def _update_grid_preview(self):
        if self.preview_image_bgr is None:
            return

        region = self._current_ocr_region() if self.cv_checkbox.isChecked() else None
        pixmap = render_grid_preview(
            self.preview_image_bgr, self.rows_spin.value(), self.cols_spin.value(), region
        )
        scaled = pixmap.scaled(
            self.preview_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setPixmap(scaled)

    def on_grid_params_changed(self):
        self._update_grid_preview()

    def on_cv_toggle(self, checked):
        self.region_group.setEnabled(checked)
        self.engine_group.setEnabled(checked)
        self._update_grid_preview()

    def on_ocr_region_changed(self):
        self._update_grid_preview()

    # ------------------------------------------------------------------ run
    def on_run(self):
        self._set_controls_enabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        self._log("Starting run…")

        self.split_worker = SplitJobWorker(
            self.input_folder,
            self.output_folder,
            self.rows_spin.value(),
            self.cols_spin.value(),
            self.cv_checkbox.isChecked(),
            ocr_region=self._current_ocr_region(),
            gpu=self._current_gpu_choice(),
            output_format=self._current_output_format(),
        )
        self.split_worker.progress.connect(self.on_job_progress)
        self.split_worker.error.connect(self.on_job_error)
        self.split_worker.finished_ok.connect(self.on_job_finished)
        self.split_worker.start()

    def on_stop(self):
        if self.split_worker is not None and self.split_worker.isRunning():
            self.split_worker.requestInterruption()
            self.stop_btn.setEnabled(False)
            self._log("Stopping… finishing the current panel first.")

    def on_job_progress(self, fraction, message):
        self.progress_bar.setValue(int(fraction * 100))
        self._log(message)

    def on_job_error(self, message):
        self._set_controls_enabled(True)
        self.stop_btn.setEnabled(False)
        self._show_error(
            message,
            details="See segmetric_tag.log inside the output folder's 'panels' directory "
            "for technical details.",
        )
        self._log(f"ERROR: {message}")

    def on_job_finished(self, result):
        self._set_controls_enabled(True)
        self.stop_btn.setEnabled(False)
        if result.interrupted:
            summary = f"Stopped — {result.panels_saved} panel(s) saved to {result.output_dir}."
        else:
            summary = f"Done — {result.panels_saved} panel(s) saved to {result.output_dir}."
        if result.files_skipped:
            summary += f"\n{len(result.files_skipped)} file(s) were skipped — see status log."
            for fname, reason in result.files_skipped:
                self._log(f"Skipped {fname}: {reason}")
        self._log(summary)
        title = "SegMetric.Tag — Stopped" if result.interrupted else "SegMetric.Tag — Run complete"
        QMessageBox.information(self, title, summary)
