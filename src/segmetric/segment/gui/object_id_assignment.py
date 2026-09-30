
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from segmetric.errors import SegMetricError

from ..core.model import PresetGroup
from ..core.presets import load_object_id_mapping, save_object_id_mapping
from .preset_editor import SegmentPresetEditorWidget


class _GroupRow(QGroupBox):
    changed = pyqtSignal()
    remove_requested = pyqtSignal(object)  # self

    def __init__(self, index, parent=None):
        super().__init__(f"Group {index}", parent)
        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.object_ids_edit = QLineEdit()
        self.object_ids_edit.setPlaceholderText("e.g. AA, AB")
        self.object_ids_edit.textChanged.connect(self.changed.emit)
        form.addRow("Object IDs:", self.object_ids_edit)
        layout.addLayout(form)

        self.preset_editor = SegmentPresetEditorWidget()
        layout.addWidget(self.preset_editor)

        remove_btn = QPushButton("Remove group")
        remove_btn.clicked.connect(lambda: self.remove_requested.emit(self))
        layout.addWidget(remove_btn)

    def object_ids(self):
        raw = self.object_ids_edit.text()
        return [c.strip().lstrip("_").upper() for c in raw.split(",") if c.strip()]

    def set_object_ids(self, object_ids):
        self.object_ids_edit.setText(", ".join(object_ids))

    def preset(self):
        return self.preset_editor.current_preset()

    def load_group(self, group: PresetGroup):
        self.set_object_ids(group.object_ids)
        self.preset_editor.load_settings(group.preset)


class ObjectIdAssignmentWidget(QWidget):
  
    ready_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._discovered_object_ids = []  # list[str]
        self._object_id_counts = {}  # {object_id: n}
        self._rows = []
        self._build_ui()

    def _build_ui(self):
        outer = QVBoxLayout(self)

        self.discovered_label = QLabel("No crops matched yet.")
        self.discovered_label.setWordWrap(True)
        outer.addWidget(self.discovered_label)

        self.coverage_label = QLabel("")
        self.coverage_label.setWordWrap(True)
        self.coverage_label.setStyleSheet("color: #b00000;")
        outer.addWidget(self.coverage_label)

        button_row = QHBoxLayout()
        add_btn = QPushButton("Add group")
        add_btn.clicked.connect(self.add_group)
        load_btn = QPushButton("Load Mapping Template…")
        load_btn.clicked.connect(self.on_load_mapping)
        save_btn = QPushButton("Save Mapping Template…")
        save_btn.clicked.connect(self.on_save_mapping)
        button_row.addWidget(add_btn)
        button_row.addWidget(load_btn)
        button_row.addWidget(save_btn)
        outer.addLayout(button_row)

        self.groups_container = QWidget()
        self.groups_layout = QVBoxLayout(self.groups_container)
        self.groups_layout.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.groups_container)
        outer.addWidget(scroll, stretch=1)

    #---------------------------------------------------
    def set_discovered_object_ids(self, object_id_counts: dict):
        """object_id_counts: {object_id: n_crops} -- already filtered by
        the setup screen's object-id filter checklist.
        """
        self._object_id_counts = dict(object_id_counts)
        self._discovered_object_ids = sorted(object_id_counts)
        if self._discovered_object_ids:
            summary = ", ".join(f"{c} ({n})" for c, n in sorted(object_id_counts.items()))
            self.discovered_label.setText(f"Object IDs in this batch: {summary}")
        else:
            self.discovered_label.setText("No object ids found among the matched crops.")
        self._update_coverage()

    #---------------------------------------------------------
    def add_group(self):
        row = _GroupRow(len(self._rows) + 1)
        row.changed.connect(self._update_coverage)
        row.remove_requested.connect(self._remove_group)
        row.preset_editor.name_edit.textChanged.connect(self._update_coverage)
        self._rows.append(row)
        self.groups_layout.insertWidget(self.groups_layout.count() - 1, row)
        self._update_coverage()
        return row

    def _remove_group(self, row):
        self._rows.remove(row)
        row.setParent(None)
        row.deleteLater()
        self._update_coverage()

    def clear_groups(self):
        for row in list(self._rows):
            self._remove_group(row)

    # --------------------------------------------------------
    def _claims(self):
        """Return (claimed: {object_id: [group_indices]}, unknown: set[str])."""
        claimed = {}
        unknown = set()
        for i, row in enumerate(self._rows):
            for object_id in row.object_ids():
                if object_id not in self._discovered_object_ids:
                    unknown.add(object_id)
                claimed.setdefault(object_id, []).append(i)
        return claimed, unknown

    def _update_coverage(self):
        claimed, unknown = self._claims()
        unassigned = [c for c in self._discovered_object_ids if c not in claimed]
        duplicated = [c for c, idxs in claimed.items() if len(idxs) > 1]

        messages = []
        if unassigned:
            messages.append(f"Unassigned: {', '.join(unassigned)}")
        if duplicated:
            messages.append(f"Assigned to more than one group: {', '.join(duplicated)}")
        if unknown:
            messages.append(f"Not among this batch's object ids: {', '.join(sorted(unknown))}")

        self.coverage_label.setText("  |  ".join(messages))
        ready = bool(self._discovered_object_ids) and not messages
        self.ready_changed.emit(ready)

    def is_ready(self):
        claimed, unknown = self._claims()
        unassigned = [c for c in self._discovered_object_ids if c not in claimed]
        duplicated = [c for c, idxs in claimed.items() if len(idxs) > 1]
        return bool(self._discovered_object_ids) and not unassigned and not duplicated and not unknown

    def preset_resolver(self):
        """{object_id: SegmentPreset}, once is_ready() -- undefined
        otherwise.
        """
        resolver = {}
        for row in self._rows:
            preset = row.preset()
            for object_id in row.object_ids():
                resolver[object_id] = preset
        return resolver

    #----------------------------------------------------------
    def on_load_mapping(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Load mapping template", "", "JSON files (*.json)"
        )
        if not path:
            return
        try:
            groups = load_object_id_mapping(path)
        except SegMetricError as exc:
            QMessageBox.critical(self, "SegMetric.Segment — Error", str(exc))
            return
        self.clear_groups()
        for group in groups:
            row = self.add_group()
            row.load_group(group)
        self._update_coverage()

    def on_save_mapping(self):
        if not self._rows:
            QMessageBox.warning(self, "SegMetric.Segment", "Nothing to save yet.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save mapping template", "segment_object_id_mapping.json", "JSON files (*.json)"
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        groups = [PresetGroup(object_ids=row.object_ids(), preset=row.preset()) for row in self._rows]
        try:
            save_object_id_mapping(path, groups)
        except SegMetricError as exc:
            QMessageBox.critical(self, "SegMetric.Segment — Error", str(exc))
