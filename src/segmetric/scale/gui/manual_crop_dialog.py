

import os

import cv2
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .manual_canvas import _RectCanvas


class _CropPanel(QWidget):
 

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.canvas = _RectCanvas()
        self.canvas.bbox_changed.connect(self._update_result_label)
        self.canvas.zoom_changed.connect(self._on_zoom_changed)
        layout.addWidget(self.canvas, stretch=1)

        hint = QLabel(
            "Click and drag to draw the crop region — drag again to redraw "
            "it · Scroll to zoom · hold Space and drag to pan"
        )
        hint.setStyleSheet("color: gray;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        controls_row = QHBoxLayout()
        self.zoom_label = QLabel("100%")
        controls_row.addWidget(self.zoom_label)
        fit_btn = QPushButton("🔍 Reset")
        fit_btn.clicked.connect(self.on_fit_zoom)
        controls_row.addWidget(fit_btn)

        clear_btn = QPushButton("↺ Clear Region")
        clear_btn.clicked.connect(self.canvas.clear_bbox)
        controls_row.addWidget(clear_btn)
        controls_row.addStretch(1)
        layout.addLayout(controls_row)

        self.result_label = QLabel("Click and drag to draw the crop region.")
        self.result_label.setStyleSheet("font-weight: bold;")
        self.result_label.setWordWrap(True)
        layout.addWidget(self.result_label)

    def load(self, image_bgr, reset_view=True):
        self.canvas.load(image_bgr, reset_view=reset_view)
        self._update_result_label()

    def _on_zoom_changed(self, zoom):
        self.zoom_label.setText(f"{round(zoom * 100)}%")

    def on_fit_zoom(self):
        self.canvas.reset_zoom()

    def _update_result_label(self):
        bbox = self.canvas.bbox
        if bbox is None:
            self.result_label.setText("Click and drag to draw the crop region.")
            return
        x1, y1, x2, y2 = bbox
        self.result_label.setText(f"{round(x2 - x1)} × {round(y2 - y1)} px region")

    def is_ready(self):
        return self.canvas.bbox is not None

    def current_bbox(self):
        if self.canvas.bbox is None:
            return None
        x1, y1, x2, y2 = self.canvas.bbox
        return (round(x1), round(y1), round(x2), round(y2))



class SetCropDialog(QDialog):
    """Set one manual crop region on a single representative image
    """

    def __init__(self, image_bgr, file_name, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Set Crop Region — {file_name}")
        self.resize(760, 680)

        self.result_bbox = None

        layout = QVBoxLayout(self)
        self.panel = _CropPanel()
        layout.addWidget(self.panel, stretch=1)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.on_accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self.panel.canvas.bbox_changed.connect(self._update_ok_enabled)
        self.panel.load(image_bgr)
        self._update_ok_enabled()

    def _update_ok_enabled(self):
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(self.panel.is_ready())

    def on_accept(self):
        self.result_bbox = self.panel.current_bbox()
        self.accept()


class CropReviewDialog(QDialog):
    """Click-through: set a crop region individually on every file uploaded
    """

    def __init__(self, file_paths, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set Crop Region — each image")
        self.resize(780, 720)

        self.file_paths = file_paths
        self.results = {}
        self.index = 0

        layout = QVBoxLayout(self)

        self.position_label = QLabel("")
        self.position_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.position_label)

        self.panel = _CropPanel()
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
            x1, y1, x2, y2 = self.results[name]
            self.panel.result_label.setText(f"Already set: {x2 - x1} × {y2 - y1} px region")
        self.position_label.setText(
            f"Image {self.index + 1} of {len(self.file_paths)} — {name}"
        )
        self.prev_btn.setEnabled(self.index > 0)
        self.next_btn.setEnabled(self.index < len(self.file_paths) - 1)

    def _save_current(self):
        bbox = self.panel.current_bbox()
        if bbox is not None:
            self.results[self._current_name()] = bbox

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
                f"{missing} image(s) still need a crop region set before you can "
                "close this window. Use Previous/Next to find them.",
            )
            return
        self.accept()


