"""The Landmark tab of segmetric-measure: Landmark's tool-specific settings
(optional masks folder used purely as a dimming reference, _blank
exclusion, an object-id filter). No preset/batch-type concept -- landmark
placement is freeform, same as its standalone tool. Scales file / Crops
folder / Output folder / Metadata preset all live once on the shared
MainWindow -- see refresh_object_id_filter(), called by MainWindow
whenever any of that shared state changes, mirroring
segmetric.landmark.gui.setup_window.SetupPage's own reactive
_refresh_object_id_filter (untouched, still used standalone).
"""
from PyQt6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from segmetric.errors import SegMetricError
from segmetric.prepare.core.metadata import apply_preset_to_filename
from segmetric.segment.core.matching import match_crops


class LandmarkTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.masks_folder = None
        self._discovered_object_ids = []
        self._object_id_checkboxes = {}
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        self.enabled_checkbox = QCheckBox("Include Landmark in this run")
        self.enabled_checkbox.toggled.connect(self._on_enabled_changed)
        layout.addWidget(self.enabled_checkbox)

        inputs_group = QGroupBox("Inputs")
        inputs_layout = QFormLayout(inputs_group)

        self.masks_line = QLineEdit()
        self.masks_line.setReadOnly(True)
        self.masks_browse = QPushButton("Browse…")
        self.masks_browse.clicked.connect(self.on_browse_masks)
        self.masks_clear = QPushButton("Clear")
        self.masks_clear.clicked.connect(self.on_clear_masks)
        masks_row = QHBoxLayout()
        masks_row.addWidget(self.masks_line)
        masks_row.addWidget(self.masks_browse)
        masks_row.addWidget(self.masks_clear)
        inputs_layout.addRow("Masks folder:", masks_row)

        self.masks_hint = QLabel(
            "(Optional) segmetric.mask output applied as visual guide."
        )
        self.masks_hint.setStyleSheet("color: gray;")
        self.masks_hint.setWordWrap(True)
        inputs_layout.addRow("", self.masks_hint)

        self.remove_blank_checkbox = QCheckBox("Remove files tagged _blank")
        self.remove_blank_checkbox.setChecked(True)
        inputs_layout.addRow("", self.remove_blank_checkbox)

        self.mask_warning_label = QLabel("")
        self.mask_warning_label.setStyleSheet("color: #b06a00;")
        self.mask_warning_label.setWordWrap(True)
        inputs_layout.addRow("", self.mask_warning_label)

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

        layout.addStretch(1)
        self._on_enabled_changed(False)

    def _on_enabled_changed(self, checked):
        for w in (self.masks_browse, self.masks_clear, self.remove_blank_checkbox):
            w.setEnabled(checked)

    def set_masks_auto_chained(self, auto_chained):
        """Same cosmetic-only role as SegmentTab.set_masks_auto_chained."""
        self.masks_browse.setEnabled(not auto_chained and self.enabled_checkbox.isChecked())
        self.masks_clear.setEnabled(not auto_chained and self.enabled_checkbox.isChecked())
        if auto_chained:
            self.masks_hint.setText("Auto: using this run's Mask stage output.")
        else:
            self.masks_hint.setText(
                "Optional -- segmetric.mask output, shown as a dimmed-outside-"
                "mask visual reference only, never a constraint on where you "
                "can click. If Mask is also enabled above, this is filled in "
                "automatically from its output once you Run."
            )

    # -------------------------------------------------------------- browse
    def on_browse_masks(self):
        folder = QFileDialog.getExistingDirectory(self, "Select masks folder")
        if not folder:
            return
        self.masks_folder = folder
        self.masks_line.setText(folder)

    def on_clear_masks(self):
        self.masks_folder = None
        self.masks_line.clear()

    # ----------------------------------------------------- object-id filter
    def selected_object_ids(self):
        if not self._object_id_checkboxes:
            return None
        return {oid for oid, cb in self._object_id_checkboxes.items() if cb.isChecked()}

    def refresh_object_id_filter(self, scales_file, crops_folder, masks_dir, metadata_preset):
        self.mask_warning_label.setText("")
        preset_has_object_id = metadata_preset is not None and metadata_preset.object_id_column is not None
        ready_for_scan = scales_file and crops_folder and preset_has_object_id
        self.object_id_filter_group.setVisible(bool(ready_for_scan))
        if not ready_for_scan:
            self._discovered_object_ids = []
            self._object_id_checkboxes = {}
            self._clear_object_ids_layout()
            return

        try:
            matched, _unmatched, no_mask = match_crops(
                crops_folder, scales_file, masks_dir,
                exclude_blank_tagged=self.remove_blank_checkbox.isChecked(),
            )
        except SegMetricError:
            return  # surfaced properly when Run is actually clicked

        if masks_dir and no_mask:
            self.mask_warning_label.setText(
                f"⚠ {len(no_mask)} of {len(matched)} matched crop(s) have no usable "
                "mask and will have no dimming reference while placing landmarks."
            )

        counts = {}
        for item in matched:
            row = apply_preset_to_filename(item.original_stem, metadata_preset)
            object_id = row.get(metadata_preset.object_id_column)
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
