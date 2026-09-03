"""The Mask tab of segmetric-measure: just Mask's tool-specific settings
(single-filter vs. mixed-by-object-id, and the filter(s) themselves).
Scales file / Crops folder / Output folder / Metadata preset all live once
on the shared MainWindow instead of being repeated per tab -- see
segmetric.mask.gui.setup_window.SetupPage for the standalone tool's own,
untouched version of this page (which does bundle those fields).
"""
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QGroupBox,
    QRadioButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from segmetric.errors import SegMetricError
from segmetric.mask.core.matching import match_crops_to_scale_rows
from segmetric.mask.gui.filter_editor import FilterEditorWidget
from segmetric.mask.gui.object_id_assignment import ObjectIdAssignmentWidget
from segmetric.prepare.core.metadata import apply_preset_to_filename

BATCH_SINGLE = "single"
BATCH_MIXED = "mixed"


class MaskTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        self.enabled_checkbox = QCheckBox("Include Mask in this run")
        self.enabled_checkbox.toggled.connect(self._on_enabled_changed)
        layout.addWidget(self.enabled_checkbox)

        batch_group = QGroupBox("Batch type")
        batch_layout = QVBoxLayout(batch_group)
        self.single_radio = QRadioButton("Single Object - apply one filter for all images")
        self.single_radio.setChecked(True)
        self.mixed_radio = QRadioButton("Mixed Object - apply filters based on Object ID")
        batch_button_group = QButtonGroup(batch_group)
        batch_button_group.addButton(self.single_radio)
        batch_button_group.addButton(self.mixed_radio)
        self.single_radio.toggled.connect(self._on_batch_type_changed)
        batch_layout.addWidget(self.single_radio)
        batch_layout.addWidget(self.mixed_radio)
        self.batch_group = batch_group
        layout.addWidget(batch_group)

        self.settings_stack = QStackedWidget()
        self.filter_editor = FilterEditorWidget()
        self.settings_stack.addWidget(self.filter_editor)  # index 0 -- single
        self.object_id_widget = ObjectIdAssignmentWidget()
        self.settings_stack.addWidget(self.object_id_widget)  # index 1 -- mixed
        layout.addWidget(self.settings_stack, stretch=1)

        self._on_enabled_changed(False)

    def _on_batch_type_changed(self, _checked):
        self.settings_stack.setCurrentIndex(1 if self.mixed_radio.isChecked() else 0)

    def _on_enabled_changed(self, checked):
        self.batch_group.setEnabled(checked)
        self.settings_stack.setEnabled(checked)

    def batch_type(self):
        return BATCH_MIXED if self.mixed_radio.isChecked() else BATCH_SINGLE

    # ----------------------------------------------------- object-id assignment
    def refresh_object_id_assignment(self, scales_file, crops_folder, metadata_preset):
        """Reactively re-populate the Mixed-mode ObjectIdAssignmentWidget's
        discovered ids whenever shared Folders/Metadata state changes --
        previously this only happened once Run was clicked (matching how
        segmetric-mask's own standalone MainWindow does it), which left the
        widget showing "No crops matched yet." while typing groups in
        ahead of time. Safe to call repeatedly: set_discovered_object_ids
        only refreshes the discovered-id list/coverage check, never the
        user's own typed groups.
        """
        preset_has_object_id = metadata_preset is not None and metadata_preset.object_id_column is not None
        if not (scales_file and crops_folder and preset_has_object_id):
            self.object_id_widget.set_discovered_object_ids({})
            return

        try:
            matched, _unmatched = match_crops_to_scale_rows(crops_folder, scales_file)
        except SegMetricError:
            return  # surfaced properly when Run is actually clicked

        counts = {}
        for item in matched:
            row = apply_preset_to_filename(item.original_stem, metadata_preset)
            object_id = row.get(metadata_preset.object_id_column)
            if object_id:
                counts[object_id] = counts.get(object_id, 0) + 1
        self.object_id_widget.set_discovered_object_ids(counts)
