"""The Segment tab of segmetric-measure: Segment's tool-specific settings
(optional masks folder, _blank exclusion, an object-id filter to narrow
the batch, and single-preset vs. mixed-by-object-id preset assignment).
Scales file / Crops folder / Output folder / Metadata preset all live once
on the shared MainWindow -- see refresh_object_id_filter(), called by
MainWindow whenever any of that shared state changes, mirroring
segmetric.segment.gui.setup_window.SetupPage's own reactive
_refresh_object_id_filter (untouched, still used standalone) but
parameterized on shared state instead of reading self.scales_file etc.
"""
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from segmetric.errors import SegMetricError
from segmetric.prepare.core.metadata import apply_preset_to_filename
from segmetric.segment.core.matching import match_crops
from segmetric.segment.gui.object_id_assignment import ObjectIdAssignmentWidget
from segmetric.segment.gui.preset_editor import SegmentPresetEditorWidget

BATCH_SINGLE = "single"
BATCH_MIXED = "mixed"


class SegmentTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.masks_folder = None
        self._discovered_object_ids = []
        self._object_id_checkboxes = {}
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        self.enabled_checkbox = QCheckBox("Include Segment in this run")
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
            "Optional -- segmetric.mask output, used to constrain detection "
            "to the wing. If Mask is also enabled above, this is filled in "
            "automatically from its output once you Run."
        )
        self.masks_hint.setStyleSheet("color: gray;")
        self.masks_hint.setWordWrap(True)
        inputs_layout.addRow("", self.masks_hint)

        self.remove_blank_checkbox = QCheckBox("Remove files tagged _blank")
        self.remove_blank_checkbox.setChecked(True)
        self.remove_blank_checkbox.toggled.connect(self._on_local_inputs_changed)
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

        batch_group = QGroupBox("Preset assignment")
        batch_layout = QVBoxLayout(batch_group)
        self.single_radio = QRadioButton("Single preset - apply one preset for all images")
        self.single_radio.setChecked(True)
        self.mixed_radio = QRadioButton("Mixed - apply presets based on Object ID")
        batch_button_group = QButtonGroup(batch_group)
        batch_button_group.addButton(self.single_radio)
        batch_button_group.addButton(self.mixed_radio)
        self.single_radio.toggled.connect(self._on_batch_type_changed)
        batch_layout.addWidget(self.single_radio)
        batch_layout.addWidget(self.mixed_radio)
        self.batch_group = batch_group
        layout.addWidget(batch_group)

        self.settings_stack = QStackedWidget()
        self.preset_editor = SegmentPresetEditorWidget()
        self.settings_stack.addWidget(self.preset_editor)  # index 0 -- single
        self.object_id_widget = ObjectIdAssignmentWidget()
        self.settings_stack.addWidget(self.object_id_widget)  # index 1 -- mixed
        layout.addWidget(self.settings_stack, stretch=1)

        self._on_enabled_changed(False)

    # ------------------------------------------------------------- state
    def batch_type(self):
        return BATCH_MIXED if self.mixed_radio.isChecked() else BATCH_SINGLE

    def _on_batch_type_changed(self, _checked):
        self.settings_stack.setCurrentIndex(1 if self.mixed_radio.isChecked() else 0)

    def _on_enabled_changed(self, checked):
        for w in (self.masks_browse, self.masks_clear, self.remove_blank_checkbox, self.batch_group, self.settings_stack):
            w.setEnabled(checked)

    def set_masks_auto_chained(self, auto_chained):
        """Cosmetic only -- the real source of truth for where masks are
        read from is measure.core.pipeline.resolve_masks_dir at Run time,
        called with the live enabled-state of the Mask tab. This just
        keeps the masks-folder picker here from looking misleadingly
        editable when Mask is enabled and will supply masks automatically.
        """
        self.masks_browse.setEnabled(not auto_chained and self.enabled_checkbox.isChecked())
        self.masks_clear.setEnabled(not auto_chained and self.enabled_checkbox.isChecked())
        if auto_chained:
            self.masks_hint.setText("Auto: using this run's Mask stage output.")
        else:
            self.masks_hint.setText(
                "Optional -- segmetric.mask output, used to constrain detection "
                "to the wing. If Mask is also enabled above, this is filled in "
                "automatically from its output once you Run."
            )

    def _on_local_inputs_changed(self, *_args):
        pass  # MainWindow re-triggers refresh_object_id_filter with shared state

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
        """None if there's no object-id filter active at all; otherwise
        the set of object ids currently checked.
        """
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
                "mask and will fall back to segmenting the whole image."
            )

        counts = {}
        for item in matched:
            row = apply_preset_to_filename(item.original_stem, metadata_preset)
            object_id = row.get(metadata_preset.object_id_column)
            if object_id:
                counts[object_id] = counts.get(object_id, 0) + 1

        if list(counts.keys()) == self._discovered_object_ids and self._object_id_checkboxes:
            return  # unchanged -- keep the user's current checkbox choices

        self._discovered_object_ids = sorted(counts)
        self._rebuild_object_ids_layout(counts)

    def refresh_object_id_assignment(self, scales_file, crops_folder, masks_dir, metadata_preset):
        """Reactively re-populate the Mixed-mode ObjectIdAssignmentWidget's
        (preset-routing, not the filter checklist above) discovered ids
        whenever shared Folders/Metadata state changes -- previously this
        only happened once Run was clicked, matching how segmetric-
        segment's own standalone MainWindow does it. Counts respect the
        current object-id filter selection, matching what Run will
        actually pass through (see MainWindow._apply_object_id_filter).
        Safe to call repeatedly -- never touches the user's own typed
        groups, only the discovered-id list/coverage check.
        """
        preset_has_object_id = metadata_preset is not None and metadata_preset.object_id_column is not None
        if not (scales_file and crops_folder and preset_has_object_id):
            self.object_id_widget.set_discovered_object_ids({})
            return

        try:
            matched, _unmatched, _no_mask = match_crops(
                crops_folder, scales_file, masks_dir,
                exclude_blank_tagged=self.remove_blank_checkbox.isChecked(),
            )
        except SegMetricError:
            return  # surfaced properly when Run is actually clicked

        selected = self.selected_object_ids()
        counts = {}
        for item in matched:
            row = apply_preset_to_filename(item.original_stem, metadata_preset)
            object_id = row.get(metadata_preset.object_id_column)
            if object_id and (selected is None or object_id in selected):
                counts[object_id] = counts.get(object_id, 0) + 1
        self.object_id_widget.set_discovered_object_ids(counts)

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
