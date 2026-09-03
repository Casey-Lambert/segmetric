"""segmetric-measure: a shared shell over segmetric.mask + segmetric.segment
+ segmetric.landmark. One Folders section (Scales file / Crops folder /
Output folder) and one Metadata-preset load, entered once instead of per
tool; a tab per measurement type with its own enable checkbox, so any
subset can run this time. Run validates everything up front, then walks
enabled stages in a fixed Mask -> Segment -> Landmark order (skipping
disabled ones) -- Mask runs as a real background job with a progress bar,
Segment/Landmark each hand control to their own existing interactive
review window, embedded directly here. See the segmetric-measure plan
(and this repo's README) for why this can't be one unattended Run button
the way segmetric.prepare's tag+scale combination is: segment and landmark
have no batch entry point at all, only an interactive click-through.
"""
from PyQt6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from segmetric.errors import SegMetricError
from segmetric.landmark.gui.review_window import ReviewWindow as LandmarkReviewWindow
from segmetric.prepare.core.metadata import apply_preset_to_filename, preset_column_order
from segmetric.segment.gui.review_window import ReviewWindow as SegmentReviewWindow
from segmetric.set.core.presets import load_preset

from ..core.pipeline import (
    build_mask_batch,
    build_segment_or_landmark_batch,
    enabled_stage_order,
    resolve_masks_dir,
)
from ..core.summary import write_measure_summary_csv
from .landmark_tab import LandmarkTab
from .mask_stage_page import MaskStagePage
from .mask_tab import BATCH_MIXED as MASK_BATCH_MIXED
from .mask_tab import MaskTab
from .segment_tab import BATCH_MIXED as SEGMENT_BATCH_MIXED
from .segment_tab import SegmentTab

PAGE_SETUP = 0
PAGE_MASK_RUN = 1
PAGE_SEGMENT_REVIEW = 2
PAGE_LANDMARK_REVIEW = 3
PAGE_SUMMARY = 4


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SegMetric.Measure — Mask + Segment + Landmark")
        self.resize(1200, 860)

        self.scales_file = None
        self.crops_folder = None
        self.output_folder = None
        self.metadata_preset = None

        self._stage_queue = []
        self._stage_batches = {}
        self._stage_pages = {}

        self._build_ui()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        central = QWidget()
        outer = QVBoxLayout(central)

        self.stack = QStackedWidget()

        self.setup_page = self._build_setup_page()
        self.stack.addWidget(self.setup_page)  # PAGE_SETUP

        self.mask_stage_page = MaskStagePage()
        self.mask_stage_page.finished.connect(self._advance_to_next_stage)
        self.mask_stage_page.back_requested.connect(self.on_run_another_batch)
        self.stack.addWidget(self.mask_stage_page)  # PAGE_MASK_RUN

        self.segment_review = SegmentReviewWindow()
        self.segment_review.finished.connect(self._advance_to_next_stage)
        self.stack.addWidget(self.segment_review)  # PAGE_SEGMENT_REVIEW

        self.landmark_review = LandmarkReviewWindow()
        self.landmark_review.finished.connect(self._advance_to_next_stage)
        self.stack.addWidget(self.landmark_review)  # PAGE_LANDMARK_REVIEW

        self.summary_page = self._build_summary_page()
        self.stack.addWidget(self.summary_page)  # PAGE_SUMMARY

        self._stage_pages = {
            "mask": self.mask_stage_page,
            "segment": self.segment_review,
            "landmark": self.landmark_review,
        }

        outer.addWidget(self.stack, stretch=1)
        self.setCentralWidget(central)

    def _build_setup_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)

        folders_group = QGroupBox("Folders")
        folders_layout = QFormLayout(folders_group)

        self.scales_line = QLineEdit()
        self.scales_line.setReadOnly(True)
        scales_browse = QPushButton("Browse…")
        scales_browse.clicked.connect(self.on_browse_scales)
        scales_row = QHBoxLayout()
        scales_row.addWidget(self.scales_line)
        scales_row.addWidget(scales_browse)
        folders_layout.addRow("Scales file:", scales_row)

        scales_hint = QLabel("scales.csv (segmetric.scale) or summary.csv (segmetric.prepare)")
        scales_hint.setStyleSheet("color: gray;")
        folders_layout.addRow("", scales_hint)

        self.crops_line = QLineEdit()
        self.crops_line.setReadOnly(True)
        crops_browse = QPushButton("Browse…")
        crops_browse.clicked.connect(self.on_browse_crops)
        crops_row = QHBoxLayout()
        crops_row.addWidget(self.crops_line)
        crops_row.addWidget(crops_browse)
        folders_layout.addRow("Crops folder:", crops_row)

        self.output_line = QLineEdit()
        self.output_line.setReadOnly(True)
        output_browse = QPushButton("Browse…")
        output_browse.clicked.connect(self.on_browse_output)
        output_row = QHBoxLayout()
        output_row.addWidget(self.output_line)
        output_row.addWidget(output_browse)
        folders_layout.addRow("Output folder:", output_row)

        layout.addWidget(folders_group)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_metadata_tab(), "Metadata")

        self.mask_tab = MaskTab()
        self.mask_tab.enabled_checkbox.toggled.connect(self._on_mask_enabled_changed)
        self.tabs.addTab(self.mask_tab, "Mask")

        self.segment_tab = SegmentTab()
        self.tabs.addTab(self.segment_tab, "Segment")

        self.landmark_tab = LandmarkTab()
        self.tabs.addTab(self.landmark_tab, "Landmark")

        layout.addWidget(self.tabs)

        self.run_btn = QPushButton("Run")
        self.run_btn.setMinimumHeight(36)
        self.run_btn.clicked.connect(self.on_run)
        layout.addWidget(self.run_btn)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        return scroll

    def _build_metadata_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        hint = QLabel(
            "Optional. Load a preset built and saved in segmetric-set to "
            "read each crop's object id -- shared by every enabled stage "
            "below (mixed-batch filter/preset routing, the object-id "
            "filter) and added to measure_summary.csv."
        )
        hint.setStyleSheet("color: gray;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        button_row = QHBoxLayout()
        self.load_preset_btn = QPushButton("Load Preset…")
        self.load_preset_btn.clicked.connect(self.on_load_metadata_preset)
        self.clear_preset_btn = QPushButton("Clear")
        self.clear_preset_btn.clicked.connect(self.on_clear_metadata_preset)
        button_row.addWidget(self.load_preset_btn)
        button_row.addWidget(self.clear_preset_btn)
        layout.addLayout(button_row)

        self.metadata_preset_label = QLabel("No preset loaded.")
        self.metadata_preset_label.setWordWrap(True)
        layout.addWidget(self.metadata_preset_label)

        layout.addStretch(1)
        return tab

    def _build_summary_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)
        again_btn = QPushButton("Run Another Batch")
        again_btn.clicked.connect(self.on_run_another_batch)
        layout.addWidget(again_btn)
        layout.addStretch(1)
        return page

    # ------------------------------------------------------------- logging
    def _show_error(self, message):
        QMessageBox.critical(self, "SegMetric.Measure — Error", message)

    # -------------------------------------------------------------- folders
    def on_browse_scales(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select scales file", "", "CSV files (*.csv)")
        if not path:
            return
        self.scales_file = path
        self.scales_line.setText(path)
        self._refresh_object_id_widgets()

    def on_browse_crops(self):
        folder = QFileDialog.getExistingDirectory(self, "Select crops folder")
        if not folder:
            return
        self.crops_folder = folder
        self.crops_line.setText(folder)
        self._refresh_object_id_widgets()

    def on_browse_output(self):
        folder = QFileDialog.getExistingDirectory(self, "Select output folder")
        if not folder:
            return
        self.output_folder = folder
        self.output_line.setText(folder)

    # ------------------------------------------------------------- metadata
    def on_load_metadata_preset(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load metadata preset", "", "JSON files (*.json)")
        if not path:
            return
        try:
            preset = load_preset(path)
        except SegMetricError as exc:
            self._show_error(str(exc))
            return
        self.metadata_preset = preset
        object_id_note = (
            f"object-id column: {preset.object_id_column}"
            if preset.object_id_column
            else "no object-id column assigned"
        )
        self.metadata_preset_label.setText(f"Loaded '{preset.name}' ({object_id_note}).")
        self._refresh_object_id_widgets()

    def on_clear_metadata_preset(self):
        self.metadata_preset = None
        self.metadata_preset_label.setText("No preset loaded.")
        self._refresh_object_id_widgets()

    def _preset_has_object_id(self):
        return self.metadata_preset is not None and self.metadata_preset.object_id_column is not None

    # -------------------------------------------------------- masks-dir wiring
    def _on_mask_enabled_changed(self, checked):
        self.segment_tab.set_masks_auto_chained(checked)
        self.landmark_tab.set_masks_auto_chained(checked)
        self._refresh_object_id_widgets()

    def _refresh_object_id_widgets(self):
        """Re-scans and re-populates every object-id-aware widget across
        all three tabs -- both the always-reactive filter checklists
        (Segment/Landmark) and the Mixed-mode assignment widgets
        (Mask/Segment) that used to only populate once Run was clicked.
        Called whenever shared Folders/Metadata state changes.
        """
        mask_enabled = self.mask_tab.enabled_checkbox.isChecked()
        segment_masks_dir = resolve_masks_dir(self.output_folder or "", mask_enabled, self.segment_tab.masks_folder)
        landmark_masks_dir = resolve_masks_dir(self.output_folder or "", mask_enabled, self.landmark_tab.masks_folder)

        self.segment_tab.refresh_object_id_filter(
            self.scales_file, self.crops_folder, segment_masks_dir, self.metadata_preset
        )
        self.landmark_tab.refresh_object_id_filter(
            self.scales_file, self.crops_folder, landmark_masks_dir, self.metadata_preset
        )
        self.mask_tab.refresh_object_id_assignment(self.scales_file, self.crops_folder, self.metadata_preset)
        self.segment_tab.refresh_object_id_assignment(
            self.scales_file, self.crops_folder, segment_masks_dir, self.metadata_preset
        )

    # -------------------------------------------------------------------- run
    def on_run(self):
        mask_enabled = self.mask_tab.enabled_checkbox.isChecked()
        segment_enabled = self.segment_tab.enabled_checkbox.isChecked()
        landmark_enabled = self.landmark_tab.enabled_checkbox.isChecked()

        if not (mask_enabled or segment_enabled or landmark_enabled):
            self._show_error("Check at least one of Mask / Segment / Landmark to run.")
            return
        if not self.scales_file or not self.crops_folder:
            self._show_error("Choose a Scales file and Crops folder first.")
            return
        if not self.output_folder:
            self._show_error("Choose an output folder first.")
            return

        errors = []
        mask_batch = None
        segment_batch = None
        landmark_batch = None

        if mask_enabled:
            if self.mask_tab.batch_type() == MASK_BATCH_MIXED and not self._preset_has_object_id():
                errors.append("Mask: mixed-batch mode needs a metadata preset with an object-id column.")
            else:
                try:
                    matched, unmatched = build_mask_batch(self.scales_file, self.crops_folder)
                except SegMetricError as exc:
                    errors.append(f"Mask: {exc}")
                else:
                    if not matched:
                        errors.append("Mask: no crops match the scales file -- nothing to process.")
                    else:
                        mask_batch = matched
                        if self.mask_tab.batch_type() == MASK_BATCH_MIXED:
                            self._populate_object_ids(self.mask_tab.object_id_widget, matched)
                            if not self.mask_tab.object_id_widget.is_ready():
                                errors.append("Mask: every discovered object id needs a filter assigned.")

        segment_masks_dir = resolve_masks_dir(self.output_folder, mask_enabled, self.segment_tab.masks_folder)
        landmark_masks_dir = resolve_masks_dir(self.output_folder, mask_enabled, self.landmark_tab.masks_folder)

        if segment_enabled:
            if self.segment_tab.batch_type() == SEGMENT_BATCH_MIXED and not self._preset_has_object_id():
                errors.append("Segment: mixed-batch mode needs a metadata preset with an object-id column.")
            else:
                try:
                    matched, unmatched, no_mask = build_segment_or_landmark_batch(
                        self.scales_file, self.crops_folder, segment_masks_dir,
                        self.segment_tab.remove_blank_checkbox.isChecked(),
                    )
                except SegMetricError as exc:
                    errors.append(f"Segment: {exc}")
                else:
                    matched = self._apply_object_id_filter(matched, self.segment_tab.selected_object_ids())
                    if not matched:
                        errors.append("Segment: no crops match the scales file -- nothing to process.")
                    else:
                        segment_batch = matched
                        if self.segment_tab.batch_type() == SEGMENT_BATCH_MIXED:
                            self._populate_object_ids(self.segment_tab.object_id_widget, matched)
                            if not self.segment_tab.object_id_widget.is_ready():
                                errors.append("Segment: every discovered object id needs a preset assigned.")

        if landmark_enabled:
            try:
                matched, unmatched, no_mask = build_segment_or_landmark_batch(
                    self.scales_file, self.crops_folder, landmark_masks_dir,
                    self.landmark_tab.remove_blank_checkbox.isChecked(),
                )
            except SegMetricError as exc:
                errors.append(f"Landmark: {exc}")
            else:
                matched = self._apply_object_id_filter(matched, self.landmark_tab.selected_object_ids())
                if not matched:
                    errors.append("Landmark: no crops match the scales file -- nothing to process.")
                else:
                    landmark_batch = matched

        if errors:
            self._show_error("\n".join(errors))
            return

        self._stage_queue = enabled_stage_order(mask_enabled, segment_enabled, landmark_enabled)
        self._stage_batches = {"mask": mask_batch, "segment": segment_batch, "landmark": landmark_batch}
        self._advance_to_next_stage()

    def _apply_object_id_filter(self, matched, selected_object_ids):
        if selected_object_ids is None:
            return matched
        preset = self.metadata_preset
        return [
            item
            for item in matched
            if apply_preset_to_filename(item.original_stem, preset).get(preset.object_id_column)
            in selected_object_ids
        ]

    def _populate_object_ids(self, object_id_widget, matched):
        preset = self.metadata_preset
        counts = {}
        for item in matched:
            row = apply_preset_to_filename(item.original_stem, preset)
            object_id = row.get(preset.object_id_column)
            if object_id:
                counts[object_id] = counts.get(object_id, 0) + 1
        object_id_widget.set_discovered_object_ids(counts)

    # --------------------------------------------------------- stage sequencing
    def _advance_to_next_stage(self):
        if not self._stage_queue:
            self._show_summary()
            return

        stage_name = self._stage_queue.pop(0)
        page = self._stage_pages[stage_name]

        if stage_name == "mask":
            matched = self._stage_batches["mask"]
            if self.mask_tab.batch_type() == MASK_BATCH_MIXED:
                filter_resolver = self.mask_tab.object_id_widget.filter_resolver()
            else:
                filter_resolver = self.mask_tab.filter_editor.current_settings()
            self.stack.setCurrentIndex(PAGE_MASK_RUN)
            page.start(matched, filter_resolver, self.output_folder, metadata_preset=self.metadata_preset)
        elif stage_name == "segment":
            matched = self._stage_batches["segment"]
            if self.segment_tab.batch_type() == SEGMENT_BATCH_MIXED:
                preset_resolver = self.segment_tab.object_id_widget.preset_resolver()
            else:
                preset_resolver = self.segment_tab.preset_editor.current_preset()
            self.stack.setCurrentIndex(PAGE_SEGMENT_REVIEW)
            page.start(matched, preset_resolver, self.metadata_preset, self.output_folder)
        elif stage_name == "landmark":
            matched = self._stage_batches["landmark"]
            self.stack.setCurrentIndex(PAGE_LANDMARK_REVIEW)
            page.start(matched, self.metadata_preset, self.output_folder)

    def _show_summary(self):
        columns = preset_column_order(self.metadata_preset) if self.metadata_preset else []
        summary_path = write_measure_summary_csv(self.output_folder, metadata_columns=columns)
        if summary_path:
            text = f"Done. Combined summary written to:\n{summary_path}"
        else:
            text = "Done. (No stage produced a CSV to summarize.)"
        self.summary_label.setText(text)
        self.stack.setCurrentIndex(PAGE_SUMMARY)

    def on_run_another_batch(self):
        self.stack.setCurrentIndex(PAGE_SETUP)
