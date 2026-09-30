
import math
import numpy as np
from PyQt6.QtCore import QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QWidget

from ..core.manual import clamp_bbox

MIN_ZOOM = 1.0
MAX_ZOOM = 8.0
ZOOM_STEP = 1.15

_CLICK_TOLERANCE_PX = 12
_POINT_RADIUS = 5
_POINT_COLOR = QColor(255, 195, 0)
_LINE_COLOR = QColor(255, 195, 0)
_RECT_COLOR = QColor(50, 220, 90)


def _bgr_to_qpixmap(image_bgr):
    rgb = np.ascontiguousarray(image_bgr[:, :, ::-1])
    height, width, _ = rgb.shape
    bytes_per_line = 3 * width
    qimage = QImage(rgb.data, width, height, bytes_per_line, QImage.Format.Format_RGB888)
    return QPixmap.fromImage(qimage.copy())


class _ZoomPanMixin:
   

    def _init_zoom_pan(self):
        self.zoom = MIN_ZOOM
        self.pan_center = None  # (ix, iy) image point at the widget's center
        self._base_scale = 1.0
        self._effective_scale = 1.0
        self._display_rect = QRect()
        self._space_held = False
        self._panning = False
        self._pan_last_widget_pt = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def reset_zoom(self, center=None):
        self.zoom = MIN_ZOOM
        if center is not None:
            self.pan_center = center
        elif self.image_bgr is not None:
            h, w = self.image_bgr.shape[:2]
            self.pan_center = (w / 2, h / 2)
        self.zoom_changed.emit(self.zoom)
        self.update()

    def _recompute_geometry(self):
        if self.image_bgr is None or self.width() == 0 or self.height() == 0:
            self._display_rect = QRect()
            return
        h, w = self.image_bgr.shape[:2]
        if w == 0 or h == 0:
            self._display_rect = QRect()
            return
        if self.pan_center is None:
            self.pan_center = (w / 2, h / 2)
        else:
            self._clamp_pan()

        self._base_scale = min(self.width() / w, self.height() / h)
        self._effective_scale = self._base_scale * self.zoom

        disp_w = max(1, round(w * self._effective_scale))
        disp_h = max(1, round(h * self._effective_scale))
        x_off = round(self.width() / 2 - self.pan_center[0] * self._effective_scale)
        y_off = round(self.height() / 2 - self.pan_center[1] * self._effective_scale)
        self._display_rect = QRect(x_off, y_off, disp_w, disp_h)

    def _clamp_pan(self):
        if self.image_bgr is None:
            return
        h, w = self.image_bgr.shape[:2]
        self.pan_center = (
            min(max(self.pan_center[0], 0), w),
            min(max(self.pan_center[1], 0), h),
        )

    def _image_point_from_widget(self, wx, wy):
        if self.image_bgr is None or self._display_rect.width() == 0:
            return None
        if not self._display_rect.contains(round(wx), round(wy)):
            return None
        h, w = self.image_bgr.shape[:2]
        rel_x = (wx - self._display_rect.x()) / self._display_rect.width()
        rel_y = (wy - self._display_rect.y()) / self._display_rect.height()
        return (rel_x * w, rel_y * h)

    def _image_point_at(self, wx, wy):
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

    def _draw_base_image(self, painter):
        if self.image_bgr is None or self._display_rect.width() == 0:
            return
        h, w = self.image_bgr.shape[:2]
        scale = self._effective_scale
        ix0 = max(0, int((0 - self._display_rect.x()) / scale))
        iy0 = max(0, int((0 - self._display_rect.y()) / scale))
        ix1 = min(w, int((self.width() - self._display_rect.x()) / scale) + 1)
        iy1 = min(h, int((self.height() - self._display_rect.y()) / scale) + 1)
        if ix1 <= ix0 or iy1 <= iy0:
            return
        visible = self.image_bgr[iy0:iy1, ix0:ix1]
        pixmap = _bgr_to_qpixmap(visible)
        dest_w = max(1, round((ix1 - ix0) * scale))
        dest_h = max(1, round((iy1 - iy0) * scale))
        scaled = pixmap.scaled(
            dest_w, dest_h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation
        )
        dest_x = round(self._display_rect.x() + ix0 * scale)
        dest_y = round(self._display_rect.y() + iy0 * scale)
        painter.drawPixmap(dest_x, dest_y, scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._recompute_geometry()

    def wheelEvent(self, event):
        if self.image_bgr is None:
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
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_held = False
            if not self._panning:
                self.unsetCursor()
        else:
            super().keyReleaseEvent(event)

    def _try_start_pan(self, pos):
        if not self._space_held:
            return False
        self._panning = True
        self._pan_last_widget_pt = (pos.x(), pos.y())
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        return True

    def _try_continue_pan(self, pos):
        if not (self._panning and self._pan_last_widget_pt is not None):
            return False
        dx = pos.x() - self._pan_last_widget_pt[0]
        dy = pos.y() - self._pan_last_widget_pt[1]
        scale = self._effective_scale or 1.0
        self.pan_center = (self.pan_center[0] - dx / scale, self.pan_center[1] - dy / scale)
        self._clamp_pan()
        self._pan_last_widget_pt = (pos.x(), pos.y())
        self.update()
        return True

    def _try_end_pan(self):
        if not self._panning:
            return False
        self._panning = False
        self._pan_last_widget_pt = None
        self.setCursor(Qt.CursorShape.OpenHandCursor) if self._space_held else self.unsetCursor()
        return True


class _TwoPointCanvas(_ZoomPanMixin, QWidget):

    points_changed = pyqtSignal()
    zoom_changed = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.image_bgr = None
        self.points = []  # 0, 1, or 2 (ix, iy)
        self._dragging_index = None
        self._init_zoom_pan()
        self.setMinimumSize(420, 320)

    def load(self, image_bgr, reset_view=True):
        self.image_bgr = image_bgr
        self.points = []
        self._dragging_index = None
        h, w = image_bgr.shape[:2]
        if reset_view or self.pan_center is None:
            self.reset_zoom(center=(w / 2, h / 2))
        else:
            self._clamp_pan()
            self.update()

    def clear_points(self):
        self.points = []
        self._dragging_index = None
        self.points_changed.emit()
        self.update()

    def pixel_distance(self):
        if len(self.points) != 2:
            return None
        (x1, y1), (x2, y2) = self.points
        return math.hypot(x2 - x1, y2 - y1)

    def _hit_test(self, wx, wy, tol=_CLICK_TOLERANCE_PX):
        for i, (ix, iy) in enumerate(self.points):
            pwx, pwy = self._widget_point_from_image(ix, iy)
            if math.hypot(wx - pwx, wy - pwy) < tol:
                return i
        return None

    def paintEvent(self, event):
        self._recompute_geometry()
        painter = QPainter(self)
        self._draw_base_image(painter)

        if len(self.points) == 2:
            (x1, y1), (x2, y2) = self.points
            wx1, wy1 = self._widget_point_from_image(x1, y1)
            wx2, wy2 = self._widget_point_from_image(x2, y2)
            pen = QPen(_LINE_COLOR)
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawLine(int(wx1), int(wy1), int(wx2), int(wy2))

        for ix, iy in self.points:
            wx, wy = self._widget_point_from_image(ix, iy)
            painter.setBrush(_POINT_COLOR)
            painter.setPen(QPen(QColor(0, 0, 0), 1))
            r = _POINT_RADIUS
            painter.drawEllipse(int(wx - r), int(wy - r), r * 2, r * 2)
        painter.end()

    def mousePressEvent(self, event):
        if self.image_bgr is None or event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position()
        self.setFocus()

        if self._try_start_pan(pos):
            return

        hit = self._hit_test(pos.x(), pos.y())
        if hit is not None:
            self._dragging_index = hit
            return

        pt = self._image_point_from_widget(pos.x(), pos.y())
        if pt is None:
            return

        if len(self.points) >= 2:
            self.points = []  # a third click starts over the click sequence
        self.points.append(pt)
        self.points_changed.emit()
        self.update()

    def mouseMoveEvent(self, event):
        pos = event.position()
        if self._try_continue_pan(pos):
            return
        if self._dragging_index is not None:
            pt = self._image_point_from_widget(pos.x(), pos.y())
            if pt is not None:
                self.points[self._dragging_index] = pt
                self.points_changed.emit()
                self.update()

    def mouseReleaseEvent(self, event):
        if self._try_end_pan():
            return
        self._dragging_index = None

##Selective croping 
class _RectCanvas(_ZoomPanMixin, QWidget):

    bbox_changed = pyqtSignal()
    zoom_changed = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.image_bgr = None
        self.bbox = None  # (x1, y1, x2, y2) in image coords, or None
        self._drag_start = None
        self._init_zoom_pan()
        self.setMinimumSize(420, 320)

    def load(self, image_bgr, reset_view=True):
        self.image_bgr = image_bgr
        self.bbox = None
        self._drag_start = None
        h, w = image_bgr.shape[:2]
        if reset_view or self.pan_center is None:
            self.reset_zoom(center=(w / 2, h / 2))
        else:
            self._clamp_pan()
            self.update()

    def clear_bbox(self):
        self.bbox = None
        self._drag_start = None
        self.bbox_changed.emit()
        self.update()

    def paintEvent(self, event):
        self._recompute_geometry()
        painter = QPainter(self)
        self._draw_base_image(painter)

        if self.bbox is not None:
            x1, y1, x2, y2 = self.bbox
            wx1, wy1 = self._widget_point_from_image(x1, y1)
            wx2, wy2 = self._widget_point_from_image(x2, y2)
            pen = QPen(_RECT_COLOR)
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawRect(int(wx1), int(wy1), int(wx2 - wx1), int(wy2 - wy1))
        painter.end()

    def mousePressEvent(self, event):
        if self.image_bgr is None or event.button() != Qt.MouseButton.LeftButton:
            return
        pos = event.position()
        self.setFocus()

        if self._try_start_pan(pos):
            return

        pt = self._image_point_from_widget(pos.x(), pos.y())
        if pt is None:
            return
        self._drag_start = pt
        self.bbox = (pt[0], pt[1], pt[0], pt[1])
        self.update()

    def mouseMoveEvent(self, event):
        pos = event.position()
        if self._try_continue_pan(pos):
            return
        if self._drag_start is None:
            return
        h, w = self.image_bgr.shape[:2]
        pt = self._image_point_at(pos.x(), pos.y())
        self.bbox = clamp_bbox((self._drag_start[0], self._drag_start[1], pt[0], pt[1]), w, h)
        self.update()

    def mouseReleaseEvent(self, event):
        if self._try_end_pan():
            return
        if self._drag_start is not None:
            self._drag_start = None
            self.bbox_changed.emit()


