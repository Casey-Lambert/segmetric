
import os

import cv2
import numpy as np
from PIL import Image
from PyQt6.QtCore import QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from segmetric.prepare.core.metadata import apply_preset_to_filename

from ..core.correction import ADD, REMOVE, apply_brush_stroke
from ..core.measurement import measure_cell
from ..core.pipeline import (
    STATUS_BLANK,
    STATUS_DAMAGED,
    STATUS_MEASURED,
    apply_step_measurement,
    new_row,
    resolve_preset,
    write_csv,
)
from .worker import DetectWorker

SELECT = "select"
PAINT = "paint"

_rng = np.random.default_rng(42)
_PALETTE = _rng.integers(80, 220, size=(256, 3)).astype(np.uint8)
_SELECTED_COLOR = np.array([60, 130, 255], dtype=np.float32)
_SELECTED_ALPHA = 0.65
_UNSELECTED_ALPHA = 0.35
_PAINT_GREEN = np.array([0, 210, 0], dtype=np.float32)
_VEIN_CYAN = np.array([0, 210, 220], dtype=np.float32)
_PAINT_ALPHA = 0.55
_VEIN_ALPHA = 0.4

MASKS_SUBDIR = "segment_masks"



def _rgb_to_qpixmap(image_rgb):
    rgb = np.ascontiguousarray(image_rgb)
    height, width, _ = rgb.shape
    bytes_per_line = 3 * width
    qimage = QImage(rgb.data, width, height, bytes_per_line, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qimage.copy())


def _select_overlay(image_rgb, labeled, n_cells, selected_labels):
    vis = image_rgb.astype(np.float32)
    out = vis.copy()
    for lbl in range(1, n_cells + 1):
        region = labeled == lbl
        if not region.any():
            continue
        if lbl in selected_labels:
            color, alpha = _SELECTED_COLOR, _SELECTED_ALPHA
        else:
            color, alpha = _PALETTE[lbl % 256].astype(np.float32), _UNSELECTED_ALPHA
        out[region] = vis[region] * (1 - alpha) + color * alpha
    return out.astype(np.uint8)


def _paint_overlay(image_rgb, mask, vein_mask=None, show_veins=False):
    vis = image_rgb.astype(np.float32)
    green = np.zeros_like(vis)
    green[:, :, :] = _PAINT_GREEN
    out = np.where(mask[:, :, None] > 0, vis * (1 - _PAINT_ALPHA) + green * _PAINT_ALPHA, vis)
    if show_veins and vein_mask is not None:
        cyan = np.zeros_like(vis)
        cyan[:, :, :] = _VEIN_CYAN
        out = np.where(vein_mask[:, :, None] > 0, out * (1 - _VEIN_ALPHA) + cyan * _VEIN_ALPHA, out)
    return out.astype(np.uint8)


MIN_ZOOM = 1.0
MAX_ZOOM = 8.0
ZOOM_STEP = 1.15


class _CellCanvas(QWidget):

    stroke_finished = pyqtSignal()
    selection_changed = pyqtSignal()
    zoom_changed = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.image_rgb = None
        self.labeled = None
        self.n_cells = 0
        self.vein_mask = None
        self.show_veins = False
        self.step_mask = None  # 0/1
        self.selected_labels = set()
        self.mode = SELECT
        self.paint_mode = ADD
        self.brush_radius = 20
        self._painting = False
        self._last_point = None
        self._hover_point = None

        self.zoom = MIN_ZOOM
        self.pan_center = None  # (ix, iy) image point at the widget's center
        self._base_scale = 1.0
        self._effective_scale = 1.0
        self._display_rect = QRect() 
        self._space_held = False
        self._panning = False
        self._pan_last_widget_pt = None

        self.setMinimumSize(420, 320)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def load(self, image_rgb, labeled, n_cells, vein_mask, step_mask, selected_labels, reset_view=False):
        """snap back image to center, stops click though from visual glitchyness
        """
        self.image_rgb = image_rgb
        self.labeled = labeled
        self.n_cells = n_cells
        self.vein_mask = vein_mask
        self.step_mask = step_mask.copy()
        self.selected_labels = set(selected_labels)
        h, w = image_rgb.shape[:2]
        if reset_view or self.pan_center is None:
            self.reset_zoom(center=(w / 2, h / 2))
        else:
            self._clamp_pan()
            self.update()

    def set_mode(self, mode):
        self.mode = mode
        self.update()

    def reset_zoom(self, center=None):
        self.zoom = MIN_ZOOM
        if center is not None:
            self.pan_center = center
        elif self.image_rgb is not None:
            h, w = self.image_rgb.shape[:2]
            self.pan_center = (w / 2, h / 2)
        self.zoom_changed.emit(self.zoom)
        self.update()

    #-------------------------------------------------------------- coords
    def _recompute_geometry(self):
        if self.image_rgb is None or self.width() == 0 or self.height() == 0:
            self._display_rect = QRect()
            return
        h, w = self.image_rgb.shape[:2]
        if w == 0 or h == 0:
            self._display_rect = QRect()
            return
        if self.pan_center is None:
            self.pan_center = (w / 2, h / 2)
        else:
            self._clamp_pan()  # safe with changes image size 
        self._base_scale = min(self.width() / w, self.height() / h)
        self._effective_scale = self._base_scale * self.zoom

        disp_w = max(1, round(w * self._effective_scale))
        disp_h = max(1, round(h * self._effective_scale))
        x_off = round(self.width() / 2 - self.pan_center[0] * self._effective_scale)
        y_off = round(self.height() / 2 - self.pan_center[1] * self._effective_scale)
        self._display_rect = QRect(x_off, y_off, disp_w, disp_h)

    def _clamp_pan(self):
        if self.image_rgb is None:
            return
        h, w = self.image_rgb.shape[:2]
        self.pan_center = (
            min(max(self.pan_center[0], 0), w),
            min(max(self.pan_center[1], 0), h),
        )

    def _image_point_from_widget(self, wx, wy):
        """Image-space point under (wx, wy), used for clicks/painting
        """
        if self.image_rgb is None or self._display_rect.width() == 0:
            return None
        if not self._display_rect.contains(round(wx), round(wy)):
            return None
        h, w = self.image_rgb.shape[:2]
        rel_x = (wx - self._display_rect.x()) / self._display_rect.width()
        rel_y = (wy - self._display_rect.y()) / self._display_rect.height()
        return (rel_x * w, rel_y * h)

    def _image_point_at(self, wx, wy):
       
        if self._effective_scale == 0:
            return (0.0, 0.0)
        ix = self.pan_center[0] + (wx - self.width() / 2) / self._effective_scale
        iy = self.pan_center[1] + (wy - self.height() / 2) / self._effective_scale
        return (ix, iy)

    #-------------------------------------------------------------- paintbrush tool application 
    def paintEvent(self, event):
        self._recompute_geometry()
        painter = QPainter(self)
        if self.image_rgb is None or self._display_rect.width() == 0:
            painter.end()
            return

        if self.mode == SELECT:
            overlay = _select_overlay(self.image_rgb, self.labeled, self.n_cells, self.selected_labels)
        else:
            overlay = _paint_overlay(self.image_rgb, self.step_mask, self.vein_mask, self.show_veins)

        h, w = self.image_rgb.shape[:2]
        scale = self._effective_scale
        # efficent visualization to improve speed 
        ix0 = max(0, int((0 - self._display_rect.x()) / scale))
        iy0 = max(0, int((0 - self._display_rect.y()) / scale))
        ix1 = min(w, int((self.width() - self._display_rect.x()) / scale) + 1)
        iy1 = min(h, int((self.height() - self._display_rect.y()) / scale) + 1)

        if ix1 > ix0 and iy1 > iy0:
            visible = overlay[iy0:iy1, ix0:ix1]
            pixmap = _rgb_to_qpixmap(visible)
            dest_w = max(1, round((ix1 - ix0) * scale))
            dest_h = max(1, round((iy1 - iy0) * scale))
            scaled = pixmap.scaled(
                dest_w, dest_h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            dest_x = round(self._display_rect.x() + ix0 * scale)
            dest_y = round(self._display_rect.y() + iy0 * scale)
            painter.drawPixmap(dest_x, dest_y, scaled)

        if self.mode == PAINT and self._hover_point is not None and not self._panning:
            r = max(2, int(self.brush_radius * scale))
            wx = self._display_rect.x() + self._hover_point[0] * scale
            wy = self._display_rect.y() + self._hover_point[1] * scale
            color = QColor(80, 230, 80) if self.paint_mode == ADD else QColor(230, 80, 80)
            pen = QPen(color)
            pen.setWidth(2)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawEllipse(int(wx - r), int(wy - r), r * 2, r * 2)
        painter.end()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._recompute_geometry()

    #---------------------------------------------------- zoom & pan 
    def wheelEvent(self, event):
        if self.image_rgb is None:
            return
        self._recompute_geometry()
        delta = event.angleDelta().y()
        if delta == 0:
            return

        pos = event.position()
        anchor = self._image_point_at(pos.x(), pos.y())
        factor = ZOOM_STEP if delta > 0 else (1.0 / ZOOM_STEP)
        new_zoom = min(MAX_ZOOM, max(MIN_ZOOM, self.zoom * factor))
        if new_zoom == self.zoom:
            return

        self.zoom = new_zoom
        new_scale = self._base_scale * self.zoom
        self.pan_center = (
            anchor[0] - (pos.x() - self.width() / 2) / new_scale,
            anchor[1] - (pos.y() - self.height() / 2) / new_scale,
        )
        self._clamp_pan()
        self.zoom_changed.emit(self.zoom)
        self.update()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_held = True
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_held = False
            if not self._panning:
                self.unsetCursor()
        else:
            super().keyReleaseEvent(event)

    #-------------------------------------------------------------- mouse input
    def mousePressEvent(self, event):
        if self.image_rgb is None or event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position()

        if self._space_held:
            self._panning = True
            self._pan_last_widget_pt = (pos.x(), pos.y())
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return

        pt = self._image_point_from_widget(pos.x(), pos.y())
        if pt is None:
            return

        if self.mode == SELECT:
            ix, iy = int(round(pt[0])), int(round(pt[1]))
            lbl = int(self.labeled[iy, ix])
            if lbl > 0:
                if lbl in self.selected_labels:
                    self.selected_labels.discard(lbl)
                else:
                    self.selected_labels.add(lbl)
                self.step_mask = np.isin(self.labeled, list(self.selected_labels)).astype(np.uint8)
                self.selection_changed.emit()
                self.update()
        else:
            self._painting = True
            self.step_mask = apply_brush_stroke(
                self.step_mask, None, None, pt[0], pt[1], self.brush_radius, self.paint_mode
            )
            self._last_point = pt
            self.update()

    def mouseMoveEvent(self, event):
        pos = event.position()

        if self._panning and self._pan_last_widget_pt is not None:
            dx = pos.x() - self._pan_last_widget_pt[0]
            dy = pos.y() - self._pan_last_widget_pt[1]
            scale = self._effective_scale or 1.0
            self.pan_center = (self.pan_center[0] - dx / scale, self.pan_center[1] - dy / scale)
            self._clamp_pan()
            self._pan_last_widget_pt = (pos.x(), pos.y())
            self.update()
            return

        pt = self._image_point_from_widget(pos.x(), pos.y())
        self._hover_point = pt
        if self.mode == PAINT and self._painting and pt is not None:
            last_x, last_y = self._last_point if self._last_point else (None, None)
            self.step_mask = apply_brush_stroke(
                self.step_mask, last_x, last_y, pt[0], pt[1], self.brush_radius, self.paint_mode
            )
            self._last_point = pt
        self.update()

    def mouseReleaseEvent(self, event):
        if self._panning:
            self._panning = False
            self._pan_last_widget_pt = None
            self.setCursor(Qt.CursorShape.OpenHandCursor) if self._space_held else self.unsetCursor()
            return
        if self._painting:
            self._painting = False
            self._last_point = None
            self.stroke_finished.emit()

    def leaveEvent(self, event):
        self._hover_point = None
        self.update()


class ReviewWindow(QWidget):
    finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.matched_items = []
        self.preset_resolver = None
        self.metadata_preset = None
        self.output_folder = None
        self.masks_dir = ""
        self.csv_path = ""

        self.index = 0
        self.rows = []  
        self._status = []  # "" | measured | blank | damaged, index-aligned
        self._detection_cache = {}  # index -> (image_rgb, wing_mask, labeled, n_cells, vein_mask, warned_no_mask)
        self._step_state = {}  
        self._current_step = None
        self._detect_worker = None
        self._all_steps_seen = []  # join in order

        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        self.position_label = QLabel("")
        self.position_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.position_label)

        self.warning_label = QLabel("")
        self.warning_label.setStyleSheet("color: #b06a00;")
        self.warning_label.setWordWrap(True)
    
        self.warning_label.setFixedHeight(2 * self.warning_label.fontMetrics().height())
        layout.addWidget(self.warning_label)

        self.step_tabs_container = QWidget()
        self.step_tabs_row = QHBoxLayout(self.step_tabs_container)
        self.step_tabs_row.setContentsMargins(0, 0, 0, 0)
    
        self.step_tabs_container.setFixedHeight(QPushButton("Step").sizeHint().height())
        layout.addWidget(self.step_tabs_container)

        self.detecting_label = QLabel("")
        self.detecting_label.setStyleSheet("color: gray; font-style: italic;")
        self.detecting_label.setFixedHeight(self.detecting_label.fontMetrics().height())
        layout.addWidget(self.detecting_label)

        self.canvas = _CellCanvas()
        self.canvas.stroke_finished.connect(self._remeasure_current_step)
        self.canvas.selection_changed.connect(self._remeasure_current_step)
        self.canvas.zoom_changed.connect(self._on_zoom_changed)
        layout.addWidget(self.canvas, stretch=1)

        zoom_hint = QLabel("Scroll to zoom · hold Space and drag to pan")
        zoom_hint.setStyleSheet("color: gray;")
        layout.addWidget(zoom_hint)

        mode_row = QHBoxLayout()
        self.select_radio = QRadioButton("Select Cells")
        self.select_radio.setChecked(True)
        self.select_radio.toggled.connect(self._on_mode_toggle)
        self.paint_radio = QRadioButton("Correct Mask")
        mode_row.addWidget(self.select_radio)
        mode_row.addWidget(self.paint_radio)

        self.add_radio = QRadioButton("ADD")
        self.add_radio.setChecked(True)
        self.add_radio.toggled.connect(self._on_paint_mode_toggle)
        self.remove_radio = QRadioButton("REMOVE")
        mode_row.addWidget(self.add_radio)
        mode_row.addWidget(self.remove_radio)

        mode_row.addWidget(QLabel("Brush size:"))
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(3, 120)
        self.size_slider.setValue(20)
        self.size_slider.valueChanged.connect(self._on_size_changed)
        mode_row.addWidget(self.size_slider, stretch=1)

        self.veins_checkbox = QCheckBox("Show veins")
        self.veins_checkbox.toggled.connect(self._on_veins_toggled)
        mode_row.addWidget(self.veins_checkbox)

        self.zoom_label = QLabel("100%")
        mode_row.addWidget(self.zoom_label)
        fit_btn = QPushButton("🔍 Fit")
        fit_btn.clicked.connect(self.on_fit_zoom)
        mode_row.addWidget(fit_btn)

        reset_btn = QPushButton("↺ Reset step")
        reset_btn.clicked.connect(self.on_reset_step)
        mode_row.addWidget(reset_btn)
        layout.addLayout(mode_row)

        status_row = QHBoxLayout()
        self.blank_btn = QPushButton("☐ Mark Blank")
        self.blank_btn.setCheckable(True)
        self.blank_btn.clicked.connect(self.on_mark_blank)
        self.damaged_btn = QPushButton("⚠ Mark Damaged")
        self.damaged_btn.setCheckable(True)
        self.damaged_btn.clicked.connect(self.on_mark_damaged)
        status_row.addWidget(self.blank_btn)
        status_row.addWidget(self.damaged_btn)
        layout.addLayout(status_row)

        self.measure_label = QLabel("")
        self.measure_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.measure_label)

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

    #-------------------------------------------------------
    def start(self, matched_items, preset_resolver, metadata_preset, output_folder):
        self.matched_items = matched_items
        self.preset_resolver = preset_resolver
        self.metadata_preset = metadata_preset
        self.output_folder = output_folder
        self.masks_dir = os.path.join(output_folder, MASKS_SUBDIR)
        os.makedirs(self.masks_dir, exist_ok=True)
        self.csv_path = os.path.join(output_folder, "segment_measurements.csv")

        self.rows = [new_row(os.path.basename(item.path)) for item in matched_items]
        self._status = ["" for _ in matched_items]
        self._detection_cache = {}
        self._step_state = {}
        self._all_steps_seen = []
        self.index = 0
        self._load_index(0)

    def _current_item(self):
        return self.matched_items[self.index]

    def _resolved_preset(self):
        preset, object_id, reason = resolve_preset(
            self._current_item(), self.preset_resolver, self.metadata_preset
        )
        return preset, object_id, reason

    #----------------------------------------------------------loading 
    def _load_index(self, index):
        self.index = index
        item = self._current_item()
        total = len(self.matched_items)
        self.position_label.setText(f"Object {index + 1} of {total} — {os.path.basename(item.path)}")
        self.prev_btn.setEnabled(index > 0)
        self.next_btn.setEnabled(index < total - 1)

        status = self._status[index]
        self.blank_btn.setChecked(status == STATUS_BLANK)
        self.damaged_btn.setChecked(status == STATUS_DAMAGED)

        preset, _object_id, reason = self._resolved_preset()
        if preset is None:
            self.warning_label.setText(f"⚠ {reason}")
            self._clear_step_tabs()
            self.canvas.load(
                np.zeros((10, 10, 3), dtype=np.uint8), np.zeros((10, 10), dtype=int), 0, None,
                np.zeros((10, 10), dtype=np.uint8), set(),
            )
            self.measure_label.setText("")
            self.detecting_label.setText("")
            return

        self.warning_label.setText("")
        for step in preset.steps:
            if step not in self._all_steps_seen:
                self._all_steps_seen.append(step)

        if index in self._detection_cache:
            self._on_detection_available(index, preset)
        else:
            self._start_detection(index, item, preset)

    def _start_detection(self, index, item, preset):
        self._clear_step_tabs()
        self.detecting_label.setText("Detecting candidate cells…")
        self.canvas.setEnabled(False)

        image_bgr = cv2.imread(item.path)
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        warned_no_mask = False
        if item.mask_path:
            raw = cv2.imread(item.mask_path, cv2.IMREAD_GRAYSCALE)
            if raw is not None and raw.shape != image_rgb.shape[:2]:
                raw = cv2.resize(
                    raw, (image_rgb.shape[1], image_rgb.shape[0]), interpolation=cv2.INTER_NEAREST
                )
            if raw is not None:
                _, raw_bin = cv2.threshold(raw, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                wing_mask = (raw_bin > 127).astype(np.uint8)
            else:
                wing_mask = np.ones(image_rgb.shape[:2], dtype=np.uint8)
                warned_no_mask = True
        else:
            wing_mask = np.ones(image_rgb.shape[:2], dtype=np.uint8)
            warned_no_mask = True

        self._pending_image_rgb = image_rgb
        self._pending_wing_mask = wing_mask
        self._pending_warned_no_mask = warned_no_mask

        self._detect_worker = DetectWorker(image_rgb, wing_mask, preset.detection)
        self._detect_worker.finished_ok.connect(
            lambda labeled, n_cells, vein_mask, idx=index: self._on_detection_finished(
                idx, labeled, n_cells, vein_mask
            )
        )
        self._detect_worker.error.connect(self._on_detection_error)
        self._detect_worker.start()

    def _on_detection_finished(self, index, labeled, n_cells, vein_mask):
        self._detection_cache[index] = (
            self._pending_image_rgb,
            self._pending_wing_mask,
            labeled,
            n_cells,
            vein_mask,
            self._pending_warned_no_mask,
        )
        self.detecting_label.setText("")
        self.canvas.setEnabled(True)
        if index == self.index:
            preset, _object_id, _reason = self._resolved_preset()
            self._on_detection_available(index, preset)

    def _on_detection_error(self, message):
        self.detecting_label.setText("")
        self.warning_label.setText(f"⚠ {message}")

    def _on_detection_available(self, index, preset):
        _image_rgb, _wing_mask, _labeled, _n_cells, _vein_mask, warned_no_mask = self._detection_cache[
            index
        ]
        if warned_no_mask:
            self.warning_label.setText(
                "⚠ No mask available for this crop — segmenting the whole image "
                "instead of just the wing/leg silhouette."
            )
        self._build_step_tabs(preset.steps)
        self._switch_step(preset.steps[0], reset_view=True)

    # ------------------------------------------------------- tabs 
    def _clear_step_tabs(self):
        while self.step_tabs_row.count():
            item = self.step_tabs_row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._current_step = None

    def _build_step_tabs(self, steps):
        self._clear_step_tabs()
        self._step_buttons = {}
        for step in steps:
            btn = QPushButton(step)
            btn.setCheckable(True)
            btn.clicked.connect(lambda _checked, s=step: self._switch_step(s))
            self.step_tabs_row.addWidget(btn)
            self._step_buttons[step] = btn
        self.step_tabs_row.addStretch(1)

    def _step_data(self, index, step):
        cache = self._step_state.setdefault(index, {})
        if step not in cache:
            _image_rgb, _wing_mask, labeled, _n_cells, _vein_mask, _warn = self._detection_cache[index]
            cache[step] = {
                "mask": np.zeros(labeled.shape, dtype=np.uint8),
                "selected": set(),
            }
        return cache[step]

    def _switch_step(self, step, reset_view=False):
        if self._current_step is not None:
            self._store_canvas_into_step(self._current_step)

        self._current_step = step
        for name, btn in getattr(self, "_step_buttons", {}).items():
            btn.setChecked(name == step)

        image_rgb, _wing_mask, labeled, n_cells, vein_mask, _warn = self._detection_cache[self.index]
        data = self._step_data(self.index, step)
        self.canvas.load(
            image_rgb, labeled, n_cells, vein_mask, data["mask"], data["selected"], reset_view=reset_view
        )
        self.select_radio.setChecked(True)
        self.canvas.set_mode(SELECT)
        self._remeasure_current_step()

    def _store_canvas_into_step(self, step):
        data = self._step_data(self.index, step)
        data["mask"] = self.canvas.step_mask.copy()
        data["selected"] = set(self.canvas.selected_labels)

    #---------------------------------------------------
    def _on_mode_toggle(self, _checked):
        self.canvas.set_mode(SELECT if self.select_radio.isChecked() else PAINT)

    def _on_paint_mode_toggle(self, _checked):
        self.canvas.paint_mode = ADD if self.add_radio.isChecked() else REMOVE

    def _on_size_changed(self, value):
        self.canvas.brush_radius = value
        self.canvas.update()

    def _on_veins_toggled(self, checked):
        self.canvas.show_veins = checked
        self.canvas.update()

    def _on_zoom_changed(self, zoom):
        self.zoom_label.setText(f"{round(zoom * 100)}%")

    def on_fit_zoom(self):
        self.canvas.reset_zoom()

    def on_reset_step(self):
        if self._current_step is None:
            return
        _image_rgb, _wing_mask, labeled, n_cells, vein_mask, _warn = self._detection_cache[self.index]
        empty = np.zeros(labeled.shape, dtype=np.uint8)
        self.canvas.load(self.canvas.image_rgb, labeled, n_cells, vein_mask, empty, set())
        self._remeasure_current_step()

    def _remeasure_current_step(self):
        if self._current_step is None or self.canvas.step_mask is None:
            self.measure_label.setText("")
            return
        item = self._current_item()
        m = measure_cell(self.canvas.step_mask, item.mm_per_pixel)
        self.measure_label.setText(
            f"{self._current_step}: W {m['bbox_w_mm']} mm × H {m['bbox_h_mm']} mm "
            f"· Area {m['area_mm2']} mm²"
        )

    #--------------------------------------------------------------- show status
    def on_mark_blank(self, checked):
        self._status[self.index] = STATUS_BLANK if checked else ""
        self.damaged_btn.setChecked(False)

    def on_mark_damaged(self, checked):
        self._status[self.index] = STATUS_DAMAGED if checked else ""
        self.blank_btn.setChecked(False)

    #------------------------------------------------------------ navigation & saving 
    def _save_current(self):
        if self._current_step is not None:
            self._store_canvas_into_step(self._current_step)

        index = self.index
        item = self.matched_items[index]
        row = self.rows[index]
        status = self._status[index]

        if status in (STATUS_BLANK, STATUS_DAMAGED):
            row["status"] = status
            for step in self._all_steps_seen:
                for suffix_field in (
                    f"{step}_area_px", f"{step}_area_mm2", f"{step}_bbox_w_px",
                    f"{step}_bbox_h_px", f"{step}_bbox_w_mm", f"{step}_bbox_h_mm",
                ):
                    row.pop(suffix_field, None)
            self._write_csv_now()
            return

        preset, object_id, _reason = self._resolved_preset()
        if preset is None:
            return

        any_measured = False
        for step in preset.steps:
            data = self._step_state.get(index, {}).get(step)
            if data is None or not data["mask"].any():
                continue
            mask_path = os.path.join(self.masks_dir, f"{item.original_stem}_{step}.png")
            Image.fromarray((data["mask"] * 255).astype(np.uint8)).save(mask_path, dpi=(1200, 1200))
            measurement = measure_cell(data["mask"], item.mm_per_pixel)
            apply_step_measurement(row, step, measurement)
            any_measured = True

        if any_measured:
            row["status"] = STATUS_MEASURED
        if object_id is not None:
            row["object_id"] = object_id
        if self.metadata_preset is not None:
            metadata_row = apply_preset_to_filename(item.original_stem, self.metadata_preset)
            for column, value in metadata_row.items():
                row[column] = value
            #record the preset file name that was used to keep records 
            row["preset_used"] = preset.name

        self._write_csv_now()

    def _write_csv_now(self):
        extra_columns = []
        include_object_id = False
        include_preset_used = False
        for row in self.rows:
            for key in row.keys():
                if key not in ("file_name", "status") and not any(
                    key.startswith(f"{s}_") for s in self._all_steps_seen
                ):
                    if key == "object_id":
                        include_object_id = True
                    elif key == "preset_used":
                        include_preset_used = True
                    elif key not in extra_columns:
                        extra_columns.append(key)
        write_csv(
            self.csv_path, self.rows, self._all_steps_seen,
            extra_columns=extra_columns,
            include_object_id=include_object_id,
            include_preset_used=include_preset_used,
        )

    def on_previous(self):
        self._save_current()
        if self.index > 0:
            self._load_index(self.index - 1)

    def on_next(self):
        self._save_current()
        if self.index < len(self.matched_items) - 1:
            self._load_index(self.index + 1)

    def on_close(self):
        self._save_current()
        self.finished.emit()




