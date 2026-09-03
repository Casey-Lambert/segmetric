import os

import cv2
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core.manual import compute_manual_scale
from .manual_canvas import _TwoPointCanvas


class _ScalePanel(QWidget):
    """Canvas + known-distance entry + live computed-scale readout --
    shared by SetScaleDialog (one representative image, for "whole batch"
    mode) and ScaleReviewDialog (click-through, one per image).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.canvas = _TwoPointCanvas()
        self.canvas.points_changed.connect(self._remeasure)
        self.canvas.zoom_changed.connect(self._on_zoom_changed)
        layout.addWidget(self.canvas, stretch=1)

        hint = QLabel(
            "Click two points on a known reference (e.g. a ruler) — a "
            "third click starts over · Scroll to zoom · hold Space and "
            "drag to pan"
        )
        hint.setStyleSheet("color: gray;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        controls_row = QHBoxLayout()
        controls_row.addWidget(QLabel("Known distance:"))
        self.distance_spin = QDoubleSpinBox()
        self.distance_spin.setRange(0.001, 1_000_000.0)
        self.distance_spin.setDecimals(3)
        self.distance_spin.setSuffix(" mm")
        self.distance_spin.setValue(1.0)
        self.distance_spin.valueChanged.connect(self._remeasure)
        controls_row.addWidget(self.distance_spin)

        self.zoom_label = QLabel("100%")
        controls_row.addWidget(self.zoom_label)
        fit_btn = QPushButton("🔍 Reset")
        fit_btn.clicked.connect(self.on_fit_zoom)
        controls_row.addWidget(fit_btn)

        clear_btn = QPushButton("↺ Clear Points")
        clear_btn.clicked.connect(self.canvas.clear_points)
        controls_row.addWidget(clear_btn)
        controls_row.addStretch(1)
        layout.addLayout(controls_row)

        self.result_label = QLabel("Click two points, then enter the distance between them.")
        self.result_label.setStyleSheet("font-weight: bold;")
        self.result_label.setWordWrap(True)
        layout.addWidget(self.result_label)

    def load(self, image_bgr, reset_view=True):
        self.canvas.load(image_bgr, reset_view=reset_view)
        self._remeasure()

    def _on_zoom_changed(self, zoom):
        self.zoom_label.setText(f"{round(zoom * 100)}%")

    def on_fit_zoom(self):
        self.canvas.reset_zoom()

    def _remeasure(self, *_args):
        mm_per_pixel = self.current_scale()
        if mm_per_pixel is None:
            self.result_label.setText("Click two points, then enter the distance between them.")
        else:
            self.result_label.setText(f"{mm_per_pixel:.6f} mm/pixel")

    def current_scale(self):
        if len(self.canvas.points) != 2:
            return None
        return compute_manual_scale(self.canvas.points[0], self.canvas.points[1], self.distance_spin.value())

    def is_ready(self):
        return self.current_scale() is not None


class SetScaleDialog(QDialog):
    """Set one manual scale on a single representative image -- used for
    "apply to whole batch" mode. Exposes .result_scale (float) after a
    successful exec()/accept().
    """

    def __init__(self, image_bgr, file_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Set Scale — {file_name}")
        self.resize(760, 680)

        self.result_scale = None

        layout = QVBoxLayout(self)
        self.panel = _ScalePanel()
        layout.addWidget(self.panel, stretch=1)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.on_accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self.panel.canvas.points_changed.connect(self._update_ok_enabled)
        self.panel.distance_spin.valueChanged.connect(self._update_ok_enabled)
        self.panel.load(image_bgr)
        self._update_ok_enabled()

    def _update_ok_enabled(self, *_args):
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(self.panel.is_ready())

    def on_accept(self):
        self.result_scale = self.panel.current_scale()
        self.accept()


class ScaleReviewDialog(QDialog):
    """Click-through: set a scale individually on every file in the batch.
    Previous/Next save the current file's scale before moving (an image
    that already has a saved value but wasn't re-clicked on this visit
    keeps its old value -- only the resulting mm/pixel number is cached,
    not the original two points, so a revisited image's canvas starts
    blank; the result label says "Already set" so that's not mistaken for
    "not set yet"). Close refuses (with a warning) until every file has a
    value. Exposes .results ({file_name: mm_per_pixel}) once accepted.
    """

    def __init__(self, file_paths, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set Scale — each image")
        self.resize(780, 720)

        self.file_paths = file_paths
        self.results = {}
        self.index = 0

        layout = QVBoxLayout(self)

        self.position_label = QLabel("")
        self.position_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.position_label)

        self.panel = _ScalePanel()
        layout.addWidget(self.panel, stretch=1)

        nav_row = QHBoxLayout()
        self.prev_btn = QPushButton("◀ Previous")
        self.prev_btn.clicked.connect(self.on_previous)
        self.next_btn = QPushButton("Next ▶")
        self.next_btn.clicked.connect(self.on_next)
        nav_row.addWidget(self.prev_btn)
        nav_row.addWidget(self.next_btn)
        nav_row.addStretch(1)
        self.close_btn = QPushButton("Close")
        self.close_btn.clicked.connect(self.on_close)
        nav_row.addWidget(self.close_btn)
        layout.addLayout(nav_row)

        self._load_current()

    def _current_name(self):
        return os.path.basename(self.file_paths[self.index])

    def _load_current(self):
        image_bgr = cv2.imread(self.file_paths[self.index])
        self.panel.load(image_bgr)
        name = self._current_name()
        if name in self.results:
            self.panel.result_label.setText(f"Already set: {self.results[name]:.6f} mm/pixel")
        self.position_label.setText(
            f"Image {self.index + 1} of {len(self.file_paths)} — {name}"
        )
        self.prev_btn.setEnabled(self.index > 0)
        self.next_btn.setEnabled(self.index < len(self.file_paths) - 1)

    def _save_current(self):
        scale = self.panel.current_scale()
        if scale is not None:
            self.results[self._current_name()] = scale

    def on_previous(self):
        self._save_current()
        if self.index > 0:
            self.index -= 1
            self._load_current()

    def on_next(self):
        self._save_current()
        if self.index < len(self.file_paths) - 1:
            self.index += 1
            self._load_current()

    def on_close(self):
        self._save_current()
        missing = len(self.file_paths) - len(self.results)
        if missing > 0:
            QMessageBox.warning(
                self, "SegMetric.Scale",
                f"{missing} image(s) still need a scale set before you can close "
                "this window. Use Previous/Next to find them.",
            )
            return
        self.accept()
