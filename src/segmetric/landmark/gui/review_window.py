import math
import os

import cv2
import numpy as np
from PyQt6.QtCore import QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from segmetric.prepare.core.metadata import apply_preset_to_filename

from ..core.measurement import landmark_field_names, landmark_row_fields
from ..core.pipeline import (
    STATUS_BLANK,
    STATUS_DAMAGED,
    STATUS_MEASURED,
    SUMMARY_FIELDS,
    new_row,
    write_csv,
)

CSV_FILENAME = "landmark_measurements.csv"


def _rgb_to_qpixmap(image_rgb):
    rgb = np.ascontiguousarray(image_rgb)
    height, width, _ = rgb.shape
    bytes_per_line = 3 * width
    qimage = QImage(rgb.data, width, height, bytes_per_line, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qimage.copy())


MIN_ZOOM = 1.0
MAX_ZOOM = 8.0
ZOOM_STEP = 1.15

_DOT_RADIUS = 5
_SELECTED_COLOR = QColor(255, 195, 0)
_PLACED_COLOR = QColor(50, 220, 90)
_DIM_FACTOR = 0.35
_CLICK_TOLERANCE_PX = 12


class _LandmarkCanvas(QWidget):
    """Shows a crop with OPTIONAL mask upload as a guide.
    Clicking empty space places a new landmark, double-clicking an existing dot lets you rename the landmark. 
    Clicking an existing dot to drag or use arrow keys to move (1px movement), 
    Delete/Backspace removes the selected dot.
    
    """

    points_changed = pyqtSignal()
    zoom_changed = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.image_rgb = None
        self.mask = None  # uint8 0/1, or None
        self.dim_outside_mask = True
        self.order = []  # placement order of labels currently in `points`
        self.points = {}  # label -> (x, y) in image coords
        self.selected_label = None
        self._dragging = False

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

    def load(self, image_rgb, mask, points, order, reset_view=False):
        """ image loaded in
        """
        self.image_rgb = image_rgb
        self.mask = mask
        self.points = dict(points)
        self.order = list(order)
        self.selected_label = None
        h, w = image_rgb.shape[:2]
        if reset_view or self.pan_center is None:
            self.reset_zoom(center=(w / 2, h / 2))
        else:
            self._clamp_pan()
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

    def delete_selected(self):
        if self.selected_label is not None and self.selected_label in self.points:
            del self.points[self.selected_label]
            if self.selected_label in self.order:
                self.order.remove(self.selected_label)
            self.selected_label = None
            self.points_changed.emit()
            self.update()

    def select_label(self, label):
        self.selected_label = label
        self.update()

    def _next_default_label(self):
        """Sequental landmarks naming
        """
        i = 1
        while str(i) in self.points:
            i += 1
        return str(i)

    # -------------------------------------------------------------- coords
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
            self._clamp_pan()  # works even if the image size has changed

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
        """Image-space point under (wx, wy). Clicks, which must land on
        image content to work.
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
        """Unclamped image-space point under (wx, wy). Using for zoom and cursor.
        """
        if self._effective_scale == 0:
            return (0.0, 0.0)
        ix = self.pan_center[0] + (wx - self.width() / 2) / self._effective_scale
        iy = self.pan_center[1] + (wy - self.height() / 2) / self._effective_scale
        return (ix, iy)

    def _widget_point_from_image(self, ix, iy):
        return (
            self._display_rect.x() + ix * self._effective_scale,
            self._display_rect.y() + iy * self._effective_scale,
        )

    def _hit_test(self, wx, wy, tol=_CLICK_TOLERANCE_PX):
        best_label, best_dist = None, tol
        for label, (ix, iy) in self.points.items():
            pwx, pwy = self._widget_point_from_image(ix, iy)
            dist = math.hypot(wx - pwx, wy - pwy)
            if dist < best_dist:
                best_dist, best_label = dist, label
        return best_label

    # -------------------------------------------------------------------- paint
    def _build_overlay(self):
        vis = self.image_rgb.astype(np.float32)
        if self.dim_outside_mask and self.mask is not None:
            dim = vis * _DIM_FACTOR
            out = np.where(self.mask[:, :, None] > 0, vis, dim)
        else:
            out = vis
        return out.astype(np.uint8)

    def paintEvent(self, event):
        self._recompute_geometry()
        painter = QPainter(self)
        if self.image_rgb is None or self._display_rect.width() == 0:
            painter.end()
            return

        overlay = self._build_overlay()
        h, w = self.image_rgb.shape[:2]
        scale = self._effective_scale
        # Visible sub-region of the image, croped before rasterizing, keeps it efficent 
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

        # The text next to each dot is the name, default to a number unless changed 
        
        for label in self.order:
            pt = self.points.get(label)
            if pt is None:
                continue
            wx, wy = self._widget_point_from_image(pt[0], pt[1])
            color = _SELECTED_COLOR if label == self.selected_label else _PLACED_COLOR
            painter.setBrush(color)
            painter.setPen(QPen(QColor(0, 0, 0), 1))
            painter.drawEllipse(int(wx - _DOT_RADIUS), int(wy - _DOT_RADIUS), _DOT_RADIUS * 2, _DOT_RADIUS * 2)
            painter.setPen(QColor(20, 20, 20))
            painter.drawText(int(wx + _DOT_RADIUS + 2), int(wy - _DOT_RADIUS - 2), label)
        painter.end()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._recompute_geometry()

    # --------------------------------------------------------- zoom mechanics 
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
            return
        if self.selected_label is not None and self.selected_label in self.points:
            nudge = {
                Qt.Key.Key_Up: (0, -1),
                Qt.Key.Key_Down: (0, 1),
                Qt.Key.Key_Left: (-1, 0),
                Qt.Key.Key_Right: (1, 0),
            }.get(event.key())
            if nudge is not None:
                x, y = self.points[self.selected_label]
                self.points[self.selected_label] = (x + nudge[0], y + nudge[1])
                self.points_changed.emit()
                self.update()
                return
            if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                self.delete_selected()
                return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_held = False
            if not self._panning:
                self.unsetCursor()
        else:
            super().keyReleaseEvent(event)

    # ----------------------------------------------------------------- mouse helpers
    def mousePressEvent(self, event):
        if self.image_rgb is None or event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position()
        self.setFocus()

        if self._space_held:
            self._panning = True
            self._pan_last_widget_pt = (pos.x(), pos.y())
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return

        hit = self._hit_test(pos.x(), pos.y())
        if hit is not None:
            self.selected_label = hit
            self._dragging = True
            self.update()
            return

        pt = self._image_point_from_widget(pos.x(), pos.y())
        if pt is None:
            return

        label = self._next_default_label()
        self.points[label] = pt
        self.order.append(label)
        self.selected_label = label
        self.points_changed.emit()
        self.update()

    def mouseDoubleClickEvent(self, event):
        if self.image_rgb is None or event.button() != Qt.MouseButton.LeftButton or self._space_held:
            return
        pos = event.position()
        hit = self._hit_test(pos.x(), pos.y())
        if hit is None:
            return
        self.selected_label = hit
        self.update()

        new_label, ok = QInputDialog.getText(self, "Rename landmark", "Name:", text=hit)
        if not ok:
            return
        new_label = new_label.strip().lstrip("_").replace(" ", "_")
        if not new_label or new_label == hit:
            return
        if new_label in self.points:
            QMessageBox.warning(
                self, "SegMetric.Landmark",
                f"'{new_label}' is already used by another landmark on this crop.",
            )
            return

        self.points[new_label] = self.points.pop(hit)
        self.order[self.order.index(hit)] = new_label
        self.selected_label = new_label
        self.points_changed.emit()
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

        if self._dragging and self.selected_label is not None:
            pt = self._image_point_from_widget(pos.x(), pos.y())
            if pt is not None:
                self.points[self.selected_label] = pt
                self.points_changed.emit()
                self.update()

    def mouseReleaseEvent(self, event):
        if self._panning:
            self._panning = False
            self._pan_last_widget_pt = None
            self.setCursor(Qt.CursorShape.OpenHandCursor) if self._space_held else self.unsetCursor()
            return
        self._dragging = False


class ReviewWindow(QWidget):
    """Workflow: Click to place a landmark,  double-click to
    rename it, drag/nudge with arrow keys to adjust,
    All navigation options save progress before leaving.
    """

    finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.matched_items = []
        self.metadata_preset = None
        self.output_folder = None
        self.csv_path = ""

        self.index = 0
        self.rows = []  # one line per image 
        self._status = []  # "" | measured | blank | damaged
        self._points = {}  # index -> {label: (x, y)}
        self._order = {}  # index -> [label, ...] in order
        self._image_cache = {}  # index -> (image_rgb, mask_or_None, warned_no_mask)
        self._all_labels_seen = []  # Join based on lables 

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

        body_row = QHBoxLayout()

        canvas_col = QVBoxLayout()
        self.canvas = _LandmarkCanvas()
        self.canvas.points_changed.connect(self._on_points_changed)
        self.canvas.zoom_changed.connect(self._on_zoom_changed)
        canvas_col.addWidget(self.canvas, stretch=1)

        zoom_hint = QLabel(
            "Click to place a new landmark · double-click an existing one to "
            "rename it · drag to adjust (arrow keys nudge by 1px) · Scroll to "
            "zoom · hold Space and drag to pan · Delete removes the selected "
            "landmark"
        )
        zoom_hint.setStyleSheet("color: gray;")
        zoom_hint.setWordWrap(True)
        canvas_col.addWidget(zoom_hint)

        control_row = QHBoxLayout()
        self.dim_mask_checkbox = QCheckBox("Dim outside mask")
        self.dim_mask_checkbox.setChecked(True)
        self.dim_mask_checkbox.toggled.connect(self._on_dim_mask_toggled)
        control_row.addWidget(self.dim_mask_checkbox)

        self.zoom_label = QLabel("100%")
        control_row.addWidget(self.zoom_label)
        fit_btn = QPushButton("🔍 Fit")
        fit_btn.clicked.connect(self.on_fit_zoom)
        control_row.addWidget(fit_btn)

        delete_btn = QPushButton("Delete Landmark")
        delete_btn.clicked.connect(self.on_delete_landmark)
        control_row.addWidget(delete_btn)

        clear_btn = QPushButton("↺ Clear All")
        clear_btn.clicked.connect(self.on_clear_all)
        control_row.addWidget(clear_btn)
        control_row.addStretch(1)
        canvas_col.addLayout(control_row)

        body_row.addLayout(canvas_col, stretch=1)

        list_col = QVBoxLayout()
        list_col.addWidget(QLabel("Landmarks"))
        self.landmark_list = QListWidget()
        self.landmark_list.setFixedWidth(180)
        self.landmark_list.itemClicked.connect(self._on_list_item_clicked)
        list_col.addWidget(self.landmark_list, stretch=1)
        body_row.addLayout(list_col)

        layout.addLayout(body_row, stretch=1)

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

    # ------------------------------------------------------------- session
    def start(self, matched_items, metadata_preset, output_folder):
        self.matched_items = matched_items
        self.metadata_preset = metadata_preset
        self.output_folder = output_folder
        self.csv_path = os.path.join(output_folder, CSV_FILENAME)

        self.rows = [new_row(os.path.basename(item.path)) for item in matched_items]
        self._status = ["" for _ in matched_items]
        self._image_cache = {}
        self._points = {}
        self._order = {}
        self._all_labels_seen = []
        self.index = 0
        self._load_index(0)

    def _current_item(self):
        return self.matched_items[self.index]

    def _object_id_for(self, item):
        """The object id from the optional segmetric.set metadata preset.
        None if no preset is loaded
        """
        if self.metadata_preset is None or self.metadata_preset.object_id_column is None:
            return None
        metadata_row = apply_preset_to_filename(item.original_stem, self.metadata_preset)
        return metadata_row.get(self.metadata_preset.object_id_column)

    # --------------------------------------------------------------- load
    def _get_image(self, index, item):
        if index in self._image_cache:
            return self._image_cache[index]

        image_bgr = cv2.imread(item.path)
        image_rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
        mask, warned_no_mask = None, False
        if item.mask_path:
            raw = cv2.imread(item.mask_path, cv2.IMREAD_GRAYSCALE)
            if raw is not None and raw.shape != image_rgb.shape[:2]:
                raw = cv2.resize(
                    raw, (image_rgb.shape[1], image_rgb.shape[0]), interpolation=cv2.INTER_NEAREST
                )
            if raw is not None:
                _, raw_bin = cv2.threshold(raw, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                mask = (raw_bin > 127).astype(np.uint8)
            else:
                warned_no_mask = True

        result = (image_rgb, mask, warned_no_mask)
        self._image_cache[index] = result
        return result

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

        image_rgb, mask, warned_no_mask = self._get_image(index, item)
        if warned_no_mask:
            self.warning_label.setText(
                "⚠ No mask available for this crop — no dimming reference; "
                "landmark placement itself is unaffected."
            )
        else:
            self.warning_label.setText("")

        points = self._points.setdefault(index, {})
        order = self._order.setdefault(index, list(points.keys()))
        self.canvas.dim_outside_mask = self.dim_mask_checkbox.isChecked()
        self.canvas.load(image_rgb, mask, points, order, reset_view=True)
        self._rebuild_landmark_list(order, points)
        self._remeasure()

    # ----------------------------------------------------------- side list
    def _rebuild_landmark_list(self, order, points):
        self.landmark_list.blockSignals(True)
        self.landmark_list.clear()
        for label in order:
            if label not in points:
                continue
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, label)
            self.landmark_list.addItem(item)
        self.landmark_list.blockSignals(False)

    def _on_list_item_clicked(self, item):
        label = item.data(Qt.ItemDataRole.UserRole)
        self.canvas.select_label(label)

    # -------------------------------------------------------------- canvas
    def _on_points_changed(self):
        self._rebuild_landmark_list(self.canvas.order, self.canvas.points)
        self._remeasure()

    def _on_zoom_changed(self, zoom):
        self.zoom_label.setText(f"{round(zoom * 100)}%")

    def on_fit_zoom(self):
        self.canvas.reset_zoom()

    def _on_dim_mask_toggled(self, checked):
        self.canvas.dim_outside_mask = checked
        self.canvas.update()

    def on_delete_landmark(self):
        self.canvas.delete_selected()

    def on_clear_all(self):
        self.canvas.points = {}
        self.canvas.order = []
        self.canvas.selected_label = None
        self.canvas.update()
        self._on_points_changed()

    def _remeasure(self):
        item = self._current_item()
        fields = landmark_row_fields(self.canvas.points, self.canvas.order, item.mm_per_pixel)
        self.measure_label.setText(
            f"{fields['n_landmarks']} placed · Centroid size: {fields['centroid_size_mm']} mm"
        )

    # --------------------------------------------------------------- status
    def on_mark_blank(self, checked):
        self._status[self.index] = STATUS_BLANK if checked else ""
        self.damaged_btn.setChecked(False)

    def on_mark_damaged(self, checked):
        self._status[self.index] = STATUS_DAMAGED if checked else ""
        self.blank_btn.setChecked(False)

    # ------------------------------------------------------------ save/nav
    def _save_current(self):
        self._points[self.index] = dict(self.canvas.points)
        self._order[self.index] = list(self.canvas.order)

        index = self.index
        item = self.matched_items[index]
        row = self.rows[index]
        status = self._status[index]
        order = self._order[index]

        for label in order:
            if label not in self._all_labels_seen:
                self._all_labels_seen.append(label)

        if status in (STATUS_BLANK, STATUS_DAMAGED):
            row["status"] = status
            for label in order:
                for field_name in landmark_field_names(label):
                    row.pop(field_name, None)
            for field_name in SUMMARY_FIELDS:
                row.pop(field_name, None)
            self._write_csv_now()
            return

        fields = landmark_row_fields(self._points[index], order, item.mm_per_pixel)
        row.update(fields)
        if fields["n_landmarks"] > 0:
            row["status"] = STATUS_MEASURED
        object_id = self._object_id_for(item)
        if object_id is not None:
            row["object_id"] = object_id
        if self.metadata_preset is not None:
            metadata_row = apply_preset_to_filename(item.original_stem, self.metadata_preset)
            for column, value in metadata_row.items():
                row[column] = value

        self._write_csv_now()

    def _write_csv_now(self):
        extra_columns = []
        include_object_id = False
        reserved = set(SUMMARY_FIELDS) | {"file_name", "status"}
        for row in self.rows:
            for key in row.keys():
                if key in reserved or any(key.startswith(f"{label}_") for label in self._all_labels_seen):
                    continue
                if key == "object_id":
                    include_object_id = True
                elif key not in extra_columns:
                    extra_columns.append(key)
        write_csv(
            self.csv_path, self.rows, self._all_labels_seen,
            extra_columns=extra_columns,
            include_object_id=include_object_id,
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
