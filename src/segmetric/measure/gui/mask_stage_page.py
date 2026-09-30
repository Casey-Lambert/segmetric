
"""Mask step """

import csv
import os

import cv2
import numpy as np
from PIL import Image
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from segmetric.mask.core.pipeline import MASK_STATUS_CORRECTED
from segmetric.mask.core.tagging import retag_mask_file, tagged_mask_filename
from segmetric.mask.gui.correction_dialog import CorrectionDialog, ReviewDialog
from segmetric.mask.gui.worker import MaskJobWorker
from segmetric.scale.gui.preview import bgr_to_qpixmap

TABLE_COLUMNS = ["", "File", "Length (mm)", "Width (mm)", "Status", "Tag", ""]


class MaskStagePage(QWidget):
    finished = pyqtSignal()  # click-to-continue
    back_requested = pyqtSignal()  # clicked "Back" to return to "Setup" 

    def __init__(self, parent=None):
        super().__init__(parent)
        self.matched_crops = []
        self.output_folder = None
        self.mask_worker = None
        self.mask_result = None
        self._crop_by_filename = {}
        self._build_ui()

    ##-------------------------------------------------------------GUI
    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("<b>Mask</b> — generating masks and measurements…"))

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        layout.addWidget(self.progress_bar)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setEnabled(False)
        self.stop_btn.setStyleSheet("QPushButton { color: #b00000; }")
        self.stop_btn.clicked.connect(self.on_stop)
        layout.addWidget(self.stop_btn)

        self.results_table = QTableWidget(0, len(TABLE_COLUMNS))
        self.results_table.setHorizontalHeaderLabels(TABLE_COLUMNS)
        self.results_table.horizontalHeader().setStretchLastSection(False)
        layout.addWidget(self.results_table, stretch=2)

        self.review_all_btn = QPushButton("Review && Correct All →")
        self.review_all_btn.setEnabled(False)
        self.review_all_btn.clicked.connect(self.on_review_all)
        layout.addWidget(self.review_all_btn)

        layout.addWidget(QLabel("Status:"))
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view, stretch=1)

        nav_row = QHBoxLayout()
        self.back_btn = QPushButton("← Back to Setup")
        self.back_btn.setVisible(False)
        self.back_btn.clicked.connect(self.back_requested.emit)
        nav_row.addWidget(self.back_btn)
        nav_row.addStretch(1)
        self.continue_btn = QPushButton("Continue →")
        self.continue_btn.setEnabled(False)
        self.continue_btn.clicked.connect(self.on_continue)
        nav_row.addWidget(self.continue_btn)
        layout.addLayout(nav_row)

    #------------------------------------------------------------ logging
    def _log(self, message):
        self.log_view.appendPlainText(message)

    def _show_error(self, message):
        QMessageBox.critical(self, "SegMetric.Measure — Mask", message)

    #-------------------------------------------------------------- start
    def start(self, matched_crops, filter_resolver, output_folder, metadata_preset=None):
        self.matched_crops = matched_crops
        self.output_folder = output_folder
        self.mask_result = None
        self._crop_by_filename = {os.path.basename(m.path): m for m in matched_crops}
        self.results_table.setRowCount(0)
        self.log_view.clear()
        self.progress_bar.setValue(0)
        self.review_all_btn.setEnabled(False)
        self.continue_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.back_btn.setVisible(False)

        self._log("Starting mask run…")
        self.mask_worker = MaskJobWorker(
            matched_crops, filter_resolver, output_folder, metadata_preset=metadata_preset
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
        self.stop_btn.setEnabled(False)
        self.back_btn.setVisible(True)
        self._show_error(message)
        self._log(f"ERROR: {message}")

    def on_job_finished(self, result):
        self.stop_btn.setEnabled(False)
        self.mask_result = result
        self._populate_table()
        self.review_all_btn.setEnabled(bool(result.rows))
        self.continue_btn.setEnabled(True)

        verb = "Stopped" if result.interrupted else "Done"
        summary = f"{verb} — {result.masks_saved} mask(s) saved. CSV: {result.csv_path}"
        if result.skipped:
            summary += f"\n{len(result.skipped)} item(s) skipped — see status log."
            for name, reason in result.skipped:
                self._log(f"Skipped {name}: {reason}")
        self._log(summary)

    #---------------------------------------------------------- results display
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
            QMessageBox.information(
                self, "SegMetric.Measure — Mask", "Nothing to review yet -- run the batch first."
            )
            return
        dialog = ReviewDialog(self, start_index=0)
        dialog.exec()

    def save_corrected_row(self, row_idx, crop, mask, measurement, tag):
        """Duck-typed target of ReviewDialog/CorrectionDialog (see mask's
        own MainWindow.save_corrected_row, ported near-verbatim): renames
        the mask PNG if the tag changed, rewrites it, updates the row/
        table/CSV.
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

    #------------------------------------------------------------
    def on_continue(self):
        self.finished.emit()


