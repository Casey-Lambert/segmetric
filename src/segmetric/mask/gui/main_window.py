import csv
import os

import cv2
import numpy as np
from PIL import Image
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from segmetric.errors import SegMetricError
from segmetric.prepare.core.metadata import apply_preset_to_filename
from segmetric.scale.gui.preview import bgr_to_qpixmap

from ..core.matching import match_crops_to_scale_rows
from ..core.pipeline import MASK_STATUS_CORRECTED
from ..core.tagging import retag_mask_file, tagged_mask_filename
from .correction_dialog import CorrectionDialog, ReviewDialog
from .filter_editor import FilterEditorWidget
from .object_id_assignment import ObjectIdAssignmentWidget
from .setup_window import BATCH_MIXED, SetupPage
from .worker import MaskJobWorker

PAGE_SETUP = 0
PAGE_FILTER = 1
PAGE_OBJECT_ID = 2
PAGE_RESULTS = 3

TABLE_COLUMNS = ["", "File", "Length (mm)", "Width (mm)", "Status", "Tag", ""]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SegMetric.Mask — Measure & Correct")
        self.resize(1100, 820)

        self.matched_crops = []
        self.unmatched_names = []
        self.output_folder = None
        self.mask_worker = None
        self.mask_result = None
        self._crop_by_filename = {}

        self._build_ui()
        self._update_nav_state()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        central = QWidget()
        outer = QVBoxLayout(central)

        self.stack = QStackedWidget()

        self.setup_page = SetupPage()
        self.setup_page.ready_changed.connect(self._update_nav_state)
        self.stack.addWidget(self.setup_page)

        self.filter_editor = FilterEditorWidget()
        self.stack.addWidget(self.filter_editor)

        self.object_id_widget = ObjectIdAssignmentWidget()
        self.object_id_widget.ready_changed.connect(self._update_nav_state)
        self.stack.addWidget(self.object_id_widget)

        self.results_page = self._build_results_page()
        self.stack.addWidget(self.results_page)

        outer.addWidget(self.stack, stretch=1)

        nav_row = QHBoxLayout()
        self.back_btn = QPushButton("← Back")
        self.back_btn.clicked.connect(self.on_back)
        self.next_btn = QPushButton("Next →")
        self.next_btn.clicked.connect(self.on_next)
        nav_row.addWidget(self.back_btn)
        nav_row.addStretch(1)
        nav_row.addWidget(self.next_btn)
        outer.addLayout(nav_row)

        self.setCentralWidget(central)

    def _build_results_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("Output folder:"))
        self.output_line = QLineEdit()
        self.output_line.setReadOnly(True)
        output_row.addWidget(self.output_line)
        output_browse = QPushButton("Browse…")
        output_browse.clicked.connect(self.on_browse_output)
        output_row.addWidget(output_browse)
        layout.addLayout(output_row)

        run_row = QHBoxLayout()
        self.run_btn = QPushButton("Run")
        self.run_btn.setMinimumHeight(32)
        self.run_btn.clicked.connect(self.on_run)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("QPushButton { color: #b00000; }")
        self.stop_btn.clicked.connect(self.on_stop)
        self.review_all_btn = QPushButton("Review && Correct All →")
        self.review_all_btn.setEnabled(False)
        self.review_all_btn.clicked.connect(self.on_review_all)
        run_row.addWidget(self.run_btn)
        run_row.addWidget(self.stop_btn)
        run_row.addWidget(self.review_all_btn)
        layout.addLayout(run_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)

        self.results_table = QTableWidget(0, len(TABLE_COLUMNS))
        self.results_table.setHorizontalHeaderLabels(TABLE_COLUMNS)
        self.results_table.horizontalHeader().setStretchLastSection(False)
        layout.addWidget(self.results_table, stretch=2)

        layout.addWidget(QLabel("Status:"))
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view, stretch=1)

        return page

    # ------------------------------------------------------------- logging
    def _log(self, message):
        self.log_view.appendPlainText(message)

    def _show_error(self, message):
        QMessageBox.critical(self, "SegMetric.Mask — Error", message)

    # --------------------------------------------------------- navigation
    def _update_nav_state(self, *_args):
        idx = self.stack.currentIndex()
        self.back_btn.setVisible(idx != PAGE_SETUP)
        self.next_btn.setVisible(idx != PAGE_RESULTS)
        if idx == PAGE_SETUP:
            self.next_btn.setEnabled(self.setup_page.is_ready())
        elif idx == PAGE_FILTER:
            self.next_btn.setEnabled(True)
        elif idx == PAGE_OBJECT_ID:
            self.next_btn.setEnabled(self.object_id_widget.is_ready())

    def on_next(self):
        idx = self.stack.currentIndex()
        if idx == PAGE_SETUP:
            if not self._begin_matching():
                return
            if self.setup_page.batch_type() == BATCH_MIXED:
                self._populate_object_ids()
                self.stack.setCurrentIndex(PAGE_OBJECT_ID)
            else:
                self.stack.setCurrentIndex(PAGE_FILTER)
        elif idx in (PAGE_FILTER, PAGE_OBJECT_ID):
            self.stack.setCurrentIndex(PAGE_RESULTS)
        self._update_nav_state()

    def on_back(self):
        idx = self.stack.currentIndex()
        if idx == PAGE_RESULTS:
            target = PAGE_OBJECT_ID if self.setup_page.batch_type() == BATCH_MIXED else PAGE_FILTER
            self.stack.setCurrentIndex(target)
        elif idx in (PAGE_FILTER, PAGE_OBJECT_ID):
            self.stack.setCurrentIndex(PAGE_SETUP)
        self._update_nav_state()

    # ----------------------------------------------------------- matching
    def _begin_matching(self):
        try:
            matched, unmatched = match_crops_to_scale_rows(
                self.setup_page.crops_folder, self.setup_page.scales_file
            )
        except SegMetricError as exc:
            self._show_error(str(exc))
            return False

        self.matched_crops = matched
        self.unmatched_names = unmatched
        self._crop_by_filename = {os.path.basename(m.path): m for m in matched}

        if not matched:
            self._show_error("No files match to scale - nothing to process.")
            return False

        if unmatched:
            preview = "\n".join(unmatched[:10])
            more = f"\n… and {len(unmatched) - 10} more" if len(unmatched) > 10 else ""
            QMessageBox.warning(
                self,
                "SegMetric.Mask",
                f"{len(unmatched)} crop(s) had no matching scale row and will "
                f"be excluded:\n{preview}{more}",
            )
        return True

    def _populate_object_ids(self):
        preset = self.setup_page.metadata_preset
        counts = {}
        for item in self.matched_crops:
            row = apply_preset_to_filename(item.original_stem, preset)
            object_id = row.get(preset.object_id_column)
            if object_id:
                counts[object_id] = counts.get(object_id, 0) + 1
        self.object_id_widget.set_discovered_object_ids(counts)

    # -------------------------------------------------------------- run
    def on_browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Select output folder")
        if not folder:
            return
        self.output_folder = folder
        self.output_line.setText(folder)

    def on_run(self):
        if not self.output_folder:
            QMessageBox.warning(self, "SegMetric.Mask", "Choose an output folder first.")
            return

        if self.setup_page.batch_type() == BATCH_MIXED:
            filter_resolver = self.object_id_widget.filter_resolver()
        else:
            filter_resolver = self.filter_editor.current_settings()

        self.run_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setValue(0)
        self._log("Starting run…")

        self.mask_worker = MaskJobWorker(
            self.matched_crops,
            filter_resolver,
            self.output_folder,
            metadata_preset=self.setup_page.metadata_preset,
        )
        self.mask_worker.progress.connect(self.on_job_progress)
        self.mask_worker.error.connect(self.on_job_error)
        self.mask_worker.finished_ok.connect(self.on_job_finished)
        self.mask_worker.start()

    def on_stop(self):
        if self.mask_worker is not None and self.mask_worker.isRunning():
            self.mask_worker.requestInterruption()
            self.stop_btn.setEnabled(False)
            self._log("Stopping… finishing the current item first.")

    def on_job_progress(self, fraction, message):
        self.progress_bar.setValue(int(fraction * 100))
        self._log(message)

    def on_job_error(self, message):
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._show_error(message)
        self._log(f"ERROR: {message}")

    def on_job_finished(self, result):
        self.run_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.mask_result = result
        self._populate_table()
        self.review_all_btn.setEnabled(bool(result.rows))

        verb = "Stopped" if result.interrupted else "Done"
        summary = f"{verb} — {result.masks_saved} mask(s) saved. CSV: {result.csv_path}"
        if result.skipped:
            summary += f"\n{len(result.skipped)} item(s) skipped — see status log."
            for name, reason in result.skipped:
                self._log(f"Skipped {name}: {reason}")

        self._log(summary)
        QMessageBox.information(self, "SegMetric.Mask — Run complete", summary)

    # ---------------------------------------------------------- results UI
    def _populate_table(self):
        self.results_table.setRowCount(0)
        for row_dict in self.mask_result.rows:
            self._append_table_row(row_dict)

    def _append_table_row(self, row_dict):
        r = self.results_table.rowCount()
        self.results_table.insertRow(r)

        thumb_label = QLabel()
        crop = self._crop_by_filename.get(row_dict["file_name"])
        if crop is not None:
            image = cv2.imread(crop.path)
            if image is not None:
                pixmap = bgr_to_qpixmap(image).scaled(
                    50, 50, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
                )
                thumb_label.setPixmap(pixmap)
        self.results_table.setCellWidget(r, 0, thumb_label)

        self.results_table.setItem(r, 1, QTableWidgetItem(row_dict["file_name"]))
        self._refresh_table_row(r)

        edit_btn = QPushButton("Edit")
        edit_btn.clicked.connect(lambda _checked, row_idx=r: self.on_edit_row(row_idx))
        self.results_table.setCellWidget(r, 6, edit_btn)

    def _refresh_table_row(self, row_idx):
        row_dict = self.mask_result.rows[row_idx]
        self.results_table.setItem(row_idx, 2, QTableWidgetItem(str(row_dict["length_mm"])))
        self.results_table.setItem(row_idx, 3, QTableWidgetItem(str(row_dict["width_mm"])))
        self.results_table.setItem(row_idx, 4, QTableWidgetItem(row_dict["mask_status"]))
        self.results_table.setItem(row_idx, 5, QTableWidgetItem(row_dict.get("tag", "")))

    def on_edit_row(self, row_idx):
        row_dict = self.mask_result.rows[row_idx]
        crop = self._crop_by_filename.get(row_dict["file_name"])
        if crop is None:
            return

        tag = row_dict.get("tag", "")
        image_bgr = cv2.imread(crop.path)
        mask_path = os.path.join(
            self.mask_result.masks_dir, tagged_mask_filename(crop.original_stem, tag)
        )
        raw = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
        if image_bgr is None or raw is None:
            self._show_error(f"Could not reload the image/mask for {row_dict['file_name']}.")
            return
        mask = (raw > 127).astype(np.uint8)

        dialog = CorrectionDialog(
            image_bgr, mask, crop.mm_per_pixel, row_dict["file_name"], tag=tag, parent=self
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        self.save_corrected_row(row_idx, crop, dialog.result_mask, dialog.result_measurement, dialog.result_tag)

    def on_review_all(self):
        if not self.mask_result or not self.mask_result.rows:
            QMessageBox.information(self, "SegMetric.Mask", "Nothing to review yet -- run the batch first.")
            return
        dialog = ReviewDialog(self, start_index=0)
        dialog.exec()

    def save_corrected_row(self, row_idx, crop, mask, measurement, tag):
        """Persist one object's corrected mask + measurement + tag: renames
        the mask PNG if the tag changed (never touches the original crop
        image), rewrites it, updates the row/table/CSV. Called by both
        CorrectionDialog (single-file Edit) and ReviewDialog (click-through)
        via this shared path, so both stay consistent.
        """
        row_dict = self.mask_result.rows[row_idx]
        old_tag = row_dict.get("tag", "")
        mask_path = retag_mask_file(self.mask_result.masks_dir, crop.original_stem, old_tag, tag)
        Image.fromarray((mask * 255).astype(np.uint8)).save(mask_path, dpi=(1200, 1200))

        row_dict.update(measurement)
        row_dict["mask_status"] = MASK_STATUS_CORRECTED
        row_dict["tag"] = tag
        self._rewrite_csv()
        self._refresh_table_row(row_idx)
        self._log(f"Saved corrected mask for {row_dict['file_name']} (tag: {tag or 'none'}).")

    def _rewrite_csv(self):
        if not self.mask_result or not self.mask_result.rows:
            return
        fieldnames = list(self.mask_result.rows[0].keys())
        with open(self.mask_result.csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for row in self.mask_result.rows:
                writer.writerow(row)
