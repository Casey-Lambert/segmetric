import os

import cv2
import numpy as np
from PyQt6.QtCore import QRect, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (
    QDialogButtonBox,
    QDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from segmetric.scale.gui.preview import bgr_to_qpixmap

from ..core.correction import ADD, REMOVE, apply_brush_stroke
from ..core.measurement import measure_object
from ..core.tagging import tagged_mask_filename

# Matches the notebook's WingMaskEditor._get_overlay exactly.
_OVERLAY_GREEN = (0, 210, 0)  # channel-order-agnostic (pure green)
_OVERLAY_MASK_ALPHA = 0.55

TAG_DAMAGE = "damage"
TAG_BLANK = "blank"


def _blend_overlay(image_bgr, mask):
    vis = image_bgr.astype(np.float32)
    green = np.zeros_like(vis)
    green[:, :, :] = _OVERLAY_GREEN
    blended = np.where(
        mask[:, :, None] > 0, vis * (1 - _OVERLAY_MASK_ALPHA) + green * _OVERLAY_MASK_ALPHA, vis
    )
    return blended.astype(np.uint8)


MIN_ZOOM = 1.0
MAX_ZOOM = 8.0
ZOOM_STEP = 1.15


class _MaskCanvas(QWidget):
    """Shows image_bgr with mask blended in green, and paints ADD/REMOVE
    brush strokes onto the mask on mouse drag. Coordinates are translated
    between widget pixels and image pixels (where the mask actually lives).

    Supports cursor-centered scroll-wheel zoom (from MIN_ZOOM=1.0, "fit to
    window", up to MAX_ZOOM) and panning by holding Space and dragging.
    Only the *visible* portion of the image is ever rasterized to a
    QPixmap (cropped from the full-size overlay array first), so zooming
    in on a large crop doesn't blow up memory/CPU the way scaling the
    whole image up would.
    """

    stroke_finished = pyqtSignal()
    zoom_changed = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.image_bgr = None
        self.mask = None
        self.brush_radius = 20
        self.mode = ADD
        self._painting = False
        self._last_point = None  # (x, y) in image coords
        self._hover_point = None

        self.zoom = MIN_ZOOM
        self.pan_center = None  # (ix, iy) image point at the widget's center
        self._base_scale = 1.0
        self._effective_scale = 1.0
        self._display_rect = QRect()  # where the *whole* image would land (may exceed the widget)
        self._space_held = False
        self._panning = False
        self._pan_last_widget_pt = None

        self.setMinimumSize(420, 320)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def set_image_and_mask(self, image_bgr, mask, reset_view=False):
        """reset_view=True snaps back to "fit to window", centered -- used
        when a genuinely new object is loaded. False (the default) keeps
        whatever zoom/pan the user had, just clamped to the new image's
        bounds -- used by "Reset" (back to the auto-generated mask), where
        jumping the view back to "fit" would be an annoying surprise.
        """
        self.image_bgr = image_bgr
        self.mask = mask.copy()
        h, w = image_bgr.shape[:2]
        if reset_view or self.pan_center is None:
            self.reset_zoom(center=(w / 2, h / 2))
        else:
            self._clamp_pan()
            self.update()

    def reset_zoom(self, center=None):
        self.zoom = MIN_ZOOM
        if center is not None:
            self.pan_center = center
        elif self.image_bgr is not None:
            h, w = self.image_bgr.shape[:2]
            self.pan_center = (w / 2, h / 2)
        self.zoom_changed.emit(self.zoom)
        self.update()

    # -------------------------------------------------------------- coords
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
            self._clamp_pan()  # safe even if the image changed size since the last load

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
        """Image-space point under (wx, wy), or None if outside the image
        (or nothing loaded) -- used for clicks/painting, which must land on
        actual image content.
        """
        if self.image_bgr is None or self._display_rect.width() == 0:
            return None
        if not self._display_rect.contains(round(wx), round(wy)):
            return None
        h, w = self.image_bgr.shape[:2]
        rel_x = (wx - self._display_rect.x()) / self._display_rect.width()
        rel_y = (wy - self._display_rect.y()) / self._display_rect.height()
        return (rel_x * w, rel_y * h)

    def _image_point_at(self, wx, wy):
        """Unclamped image-space point under (wx, wy) -- used for zoom-to-
        cursor math, where the cursor may be over letterboxed empty space.
        """
        if self._effective_scale == 0:
            return (0.0, 0.0)
        ix = self.pan_center[0] + (wx - self.width() / 2) / self._effective_scale
        iy = self.pan_center[1] + (wy - self.height() / 2) / self._effective_scale
        return (ix, iy)

    # -------------------------------------------------------------- paint
    def paintEvent(self, event):
        self._recompute_geometry()
        painter = QPainter(self)
        if self.image_bgr is None or self._display_rect.width() == 0:
            painter.end()
            return

        overlay = _blend_overlay(self.image_bgr, self.mask)

        h, w = self.image_bgr.shape[:2]
        scale = self._effective_scale
        # Visible sub-region of the image (in image pixels) -- crop *before*
        # rasterizing, so a zoomed-in view of a large crop stays cheap.
        ix0 = max(0, int((0 - self._display_rect.x()) / scale))
        iy0 = max(0, int((0 - self._display_rect.y()) / scale))
        ix1 = min(w, int((self.width() - self._display_rect.x()) / scale) + 1)
        iy1 = min(h, int((self.height() - self._display_rect.y()) / scale) + 1)

        if ix1 > ix0 and iy1 > iy0:
            visible = overlay[iy0:iy1, ix0:ix1]
            pixmap = bgr_to_qpixmap(visible)
            dest_w = max(1, round((ix1 - ix0) * scale))
            dest_h = max(1, round((iy1 - iy0) * scale))
            scaled = pixmap.scaled(
                dest_w, dest_h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            dest_x = round(self._display_rect.x() + ix0 * scale)
            dest_y = round(self._display_rect.y() + iy0 * scale)
            painter.drawPixmap(dest_x, dest_y, scaled)

        if self._hover_point is not None and not self._panning:
            r = max(2, int(self.brush_radius * scale))
            wx = self._display_rect.x() + self._hover_point[0] * scale
            wy = self._display_rect.y() + self._hover_point[1] * scale
            color = QColor(80, 230, 80) if self.mode == ADD else QColor(230, 80, 80)
            pen = QPen(color)
            pen.setWidth(2)
            pen.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawEllipse(int(wx - r), int(wy - r), r * 2, r * 2)
        painter.end()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._recompute_geometry()

    # --------------------------------------------------------- zoom / pan
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
        else:
            super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_held = False
            if not self._panning:
                self.unsetCursor()
        else:
            super().keyReleaseEvent(event)

    # -------------------------------------------------------------- mouse
    def mousePressEvent(self, event):
        if self.image_bgr is None or event.button() != Qt.MouseButton.LeftButton:
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
        self._painting = True
        self.mask = apply_brush_stroke(
            self.mask, None, None, pt[0], pt[1], self.brush_radius, self.mode
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
        if self._painting and pt is not None:
            last_x, last_y = self._last_point if self._last_point else (None, None)
            self.mask = apply_brush_stroke(
                self.mask, last_x, last_y, pt[0], pt[1], self.brush_radius, self.mode
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


class _TagControls(QWidget):
    """⚠ Damage / ☐ Blank / custom-text tagging, mutually exclusive
    (clicking the active one again clears it). The custom tag's text stays
    in the field after Apply, so it's a single click to reuse on the next
    file.
    """

    tag_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current_tag = ""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.damage_btn = QPushButton("⚠ Mark Damaged")
        self.damage_btn.setCheckable(True)
        self.damage_btn.clicked.connect(lambda: self._toggle(TAG_DAMAGE))
        layout.addWidget(self.damage_btn)

        self.blank_btn = QPushButton("☐ Mark Blank")
        self.blank_btn.setCheckable(True)
        self.blank_btn.clicked.connect(lambda: self._toggle(TAG_BLANK))
        layout.addWidget(self.blank_btn)

        self.custom_edit = QLineEdit()
        self.custom_edit.setPlaceholderText("custom tag")
        layout.addWidget(self.custom_edit, stretch=1)

        self.apply_custom_btn = QPushButton("Apply Tag")
        self.apply_custom_btn.clicked.connect(self._on_apply_custom)
        layout.addWidget(self.apply_custom_btn)

        self.status_label = QLabel("Tag: none")
        layout.addWidget(self.status_label)

    @staticmethod
    def _sanitize(text):
        return text.strip().lstrip("_").replace(" ", "_")

    def _toggle(self, name):
        self.set_tag("" if self._current_tag == name else name)

    def _on_apply_custom(self):
        text = self._sanitize(self.custom_edit.text())
        if not text:
            return
        self.set_tag("" if self._current_tag == text else text)

    def set_tag(self, tag):
        self._current_tag = tag or ""
        self.damage_btn.setChecked(self._current_tag == TAG_DAMAGE)
        self.blank_btn.setChecked(self._current_tag == TAG_BLANK)
        self.status_label.setText(f"Tag: {self._current_tag or 'none'}")
        self.tag_changed.emit(self._current_tag)

    def current_tag(self):
        return self._current_tag


class _CorrectionPanel(QWidget):
    """Canvas + brush controls + tag controls + live measurement readout --
    the reusable core shared by the single-file CorrectionDialog and the
    click-through ReviewDialog.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mm_per_pixel = 1.0
        self._auto_mask = None
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.canvas = _MaskCanvas()
        self.canvas.zoom_changed.connect(self._on_zoom_changed)
        layout.addWidget(self.canvas, stretch=1)

        zoom_hint = QLabel("Scroll to zoom · hold Space and drag to pan")
        zoom_hint.setStyleSheet("color: gray;")
        layout.addWidget(zoom_hint)

        controls_group = QGroupBox("Brush")
        controls_layout = QHBoxLayout(controls_group)

        self.add_radio = QRadioButton("ADD")
        self.add_radio.setChecked(True)
        self.add_radio.toggled.connect(self._on_mode_changed)
        self.remove_radio = QRadioButton("REMOVE")
        controls_layout.addWidget(self.add_radio)
        controls_layout.addWidget(self.remove_radio)

        controls_layout.addWidget(QLabel("Brush size:"))
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(3, 120)
        self.size_slider.setValue(20)
        self.size_slider.valueChanged.connect(self._on_size_changed)
        controls_layout.addWidget(self.size_slider, stretch=1)

        self.zoom_label = QLabel("100%")
        controls_layout.addWidget(self.zoom_label)
        fit_btn = QPushButton("🔍 Fit")
        fit_btn.clicked.connect(self.on_fit_zoom)
        controls_layout.addWidget(fit_btn)

        reset_btn = QPushButton("↺ Reset")
        reset_btn.clicked.connect(self.on_reset)
        controls_layout.addWidget(reset_btn)

        layout.addWidget(controls_group)

        self.tag_controls = _TagControls()
        layout.addWidget(self.tag_controls)

        self.measure_label = QLabel("")
        self.measure_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.measure_label)

        self.canvas.stroke_finished.connect(self._remeasure)

    def load(self, image_bgr, mask, mm_per_pixel, tag=""):
        self.mm_per_pixel = mm_per_pixel
        self._auto_mask = mask.copy()
        # A fresh object to correct -- start at "fit to window", not
        # whatever zoom/pan was left over from the previous one.
        self.canvas.set_image_and_mask(image_bgr, mask, reset_view=True)
        self.tag_controls.set_tag(tag)
        self._remeasure()

    def _on_mode_changed(self, _checked):
        self.canvas.mode = ADD if self.add_radio.isChecked() else REMOVE

    def _on_size_changed(self, value):
        self.canvas.brush_radius = value
        self.canvas.update()

    def _on_zoom_changed(self, zoom):
        self.zoom_label.setText(f"{round(zoom * 100)}%")

    def on_fit_zoom(self):
        self.canvas.reset_zoom()

    def _remeasure(self):
        m = measure_object(self.canvas.mask, self.mm_per_pixel)
        self.measure_label.setText(
            f"Length: {m['length_mm']} mm  ·  Width: {m['width_mm']} mm  ·  "
            f"Area: {m['area_mm2']} mm²"
        )
        return m

    def on_reset(self):
        # Preserve the current zoom/pan -- only the mask content resets.
        self.canvas.set_image_and_mask(self.canvas.image_bgr, self._auto_mask)
        self._remeasure()

    def current_mask(self):
        return self.canvas.mask.copy()

    def current_measurement(self):
        return self._remeasure()

    def current_tag(self):
        return self.tag_controls.current_tag()


class CorrectionDialog(QDialog):
    """Manual mask correction for a single object (§6): brush ADD/REMOVE
    over the auto-generated mask, tagging, a live length/width readout,
    Reset (back to the auto-generated mask), and Save/Cancel.
    """

    def __init__(self, image_bgr, mask, mm_per_pixel, file_name, tag="", parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Correct mask — {file_name}")
        self.resize(760, 680)

        self.result_mask = mask.copy()
        self.result_measurement = None
        self.result_tag = tag

        layout = QVBoxLayout(self)
        self.panel = _CorrectionPanel()
        layout.addWidget(self.panel, stretch=1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.panel.load(image_bgr, mask, mm_per_pixel, tag)

    def on_save(self):
        self.result_mask = self.panel.current_mask()
        self.result_measurement = self.panel.current_measurement()
        self.result_tag = self.panel.current_tag()
        self.accept()


class ReviewDialog(QDialog):
    """Click-through correction (new): navigate every matched object in one
    window. Previous/Next save the current object's mask + tag before
    moving; Close saves the current object, then returns to the results
    table. There is no Cancel here -- every navigation action saves, per
    design (unlike the single-file CorrectionDialog, which keeps its
    Save/Cancel semantics unchanged).

    main_window must provide: mask_result (with .rows, .masks_dir),
    _crop_by_filename, and save_corrected_row(row_index, crop, mask,
    measurement, tag).
    """

    def __init__(self, main_window, start_index=0, parent=None):
        super().__init__(parent or main_window)
        self.setWindowTitle("Review & Correct All")
        self.resize(780, 720)
        self.main_window = main_window
        self.index = start_index

        layout = QVBoxLayout(self)

        self.position_label = QLabel("")
        self.position_label.setStyleSheet("font-weight: bold;")
        layout.addWidget(self.position_label)

        self.panel = _CorrectionPanel()
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

    def _row_count(self):
        return len(self.main_window.mask_result.rows)

    def _current_row(self):
        return self.main_window.mask_result.rows[self.index]

    def _load_current(self):
        row = self._current_row()
        crop = self.main_window._crop_by_filename.get(row["file_name"])
        image_bgr = cv2.imread(crop.path)
        mask_path = os.path.join(
            self.main_window.mask_result.masks_dir,
            tagged_mask_filename(crop.original_stem, row.get("tag", "")),
        )
        raw = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
        mask = (raw > 127).astype(np.uint8)

        self.panel.load(image_bgr, mask, crop.mm_per_pixel, row.get("tag", ""))
        self.position_label.setText(
            f"Object {self.index + 1} of {self._row_count()} — {row['file_name']}"
        )
        self.prev_btn.setEnabled(self.index > 0)
        self.next_btn.setEnabled(self.index < self._row_count() - 1)

    def _save_current(self):
        crop = self.main_window._crop_by_filename.get(self._current_row()["file_name"])
        if crop is None:
            return
        mask = self.panel.current_mask()
        measurement = self.panel.current_measurement()
        tag = self.panel.current_tag()
        self.main_window.save_corrected_row(self.index, crop, mask, measurement, tag)

    def on_previous(self):
        self._save_current()
        if self.index > 0:
            self.index -= 1
            self._load_current()

    def on_next(self):
        self._save_current()
        if self.index < self._row_count() - 1:
            self.index += 1
            self._load_current()

    def on_close(self):
        self._save_current()
        self.accept()
