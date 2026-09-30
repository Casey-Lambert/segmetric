
import os

import cv2
from PyQt6.QtCore import QPoint
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QPolygon

from segmetric.errors import SegMetricError

from ..core.cropping import compute_crop_bbox, crop_region_from_settings
from ..core.detection import build_detector, build_prepare_detector, detect_markers
from ..core.model import ScaleSettings
from ..core.preparation import MIN_MARKERS_FOR_PREPARE, prepare_image
from ..core.scale import MIN_MARKERS_FOR_SCALE, compute_image_scale


def load_preview_image(file_path):
    image = cv2.imread(file_path)
    if image is None:
        raise SegMetricError(
            f"Could not read '{os.path.basename(file_path)}' as an image."
        )
    return image


def bgr_to_qpixmap(image_bgr):
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    rgb = rgb.copy()  # own the buffer so QImage doesn't reference freed memory
    height, width, _ = rgb.shape
    bytes_per_line = 3 * width
    qimage = QImage(
        rgb.data, width, height, bytes_per_line, QImage.Format.Format_RGB888
    )
    return QPixmap.fromImage(qimage.copy())


def _draw_markers(painter, pixmap, corners):
    marker_pen = QPen(QColor(0, 200, 0))
    marker_pen.setWidth(max(2, pixmap.width() // 400))
    painter.setPen(marker_pen)
    for marker_corners in corners:
        pts = marker_corners.reshape((4, 2))
        polygon = QPolygon([QPoint(int(x), int(y)) for x, y in pts])
        painter.drawPolygon(polygon)


def render_marker_preview(image_bgr, settings: ScaleSettings):
    detector = build_detector(settings)
    prepare_detector = build_prepare_detector(settings)
    prepared = prepare_image(
        image_bgr,
        prepare_detector,
        use_blob_fallback=settings.use_blob_fallback,
        blob_min_area=settings.prepare_blob_min_area,
        blob_max_area=settings.prepare_blob_max_area,
        blob_min_aspect=settings.blob_min_aspect,
        blob_max_aspect=settings.blob_max_aspect,
    )

    if prepared is None:
        # Can't even get past step 7
        # sample with found markers to diagnose error in detection 
        corners, ids = detect_markers(
            image_bgr,
            prepare_detector,
            use_blob_fallback=settings.use_blob_fallback,
            blob_min_area=settings.prepare_blob_min_area,
            blob_max_area=settings.prepare_blob_max_area,
            blob_min_aspect=settings.blob_min_aspect,
            blob_max_aspect=settings.blob_max_aspect,
        )
        n_found = 0 if ids is None else len(ids)
        pixmap = bgr_to_qpixmap(image_bgr)
        painter = QPainter(pixmap)
        _draw_markers(painter, pixmap, corners)
        painter.end()
        status_text = (
            f"Only {n_found} marker(s) found — needs at least "
            f"{MIN_MARKERS_FOR_PREPARE} before this panel can be prepared "
            "for measurement or cropping at all"
        )
        return pixmap, status_text

    corners, ids = detect_markers(
        prepared,
        detector,
        use_blob_fallback=settings.use_blob_fallback,
        blob_min_area=settings.final_blob_min_area,
        blob_max_area=settings.final_blob_max_area,
        blob_min_aspect=settings.blob_min_aspect,
        blob_max_aspect=settings.blob_max_aspect,
    )
    n_found = 0 if ids is None else len(ids)

    pixmap = bgr_to_qpixmap(prepared)
    painter = QPainter(pixmap)
    _draw_markers(painter, pixmap, corners)

    crop_bbox = compute_crop_bbox(
        prepared,
        detector,
        region=crop_region_from_settings(settings),
        use_blob_fallback=settings.use_blob_fallback,
        blob_min_area=settings.final_blob_min_area,
        blob_max_area=settings.final_blob_max_area,
        blob_min_aspect=settings.blob_min_aspect,
        blob_max_aspect=settings.blob_max_aspect,
    )
    if crop_bbox is not None:
        crop_pen = QPen(QColor(255, 140, 0))
        crop_pen.setWidth(max(2, pixmap.width() // 400))
        painter.setPen(crop_pen)
        x1, y1, x2, y2 = crop_bbox
        painter.drawRect(x1, y1, x2 - x1, y2 - y1)

    painter.end()

    mm_per_pixel = None
    if n_found >= MIN_MARKERS_FOR_SCALE:
        mm_per_pixel = compute_image_scale(
            prepared,
            detector,
            settings.marker_spacing_mm,
            use_blob_fallback=settings.use_blob_fallback,
            blob_min_area=settings.final_blob_min_area,
            blob_max_area=settings.final_blob_max_area,
            blob_min_aspect=settings.blob_min_aspect,
            blob_max_aspect=settings.blob_max_aspect,
        )

    if mm_per_pixel is not None:
        status_text = f"{n_found} marker(s) found — {mm_per_pixel:.6f} mm/pixel"
    elif crop_bbox is not None:
        status_text = (
            f"Only {n_found} marker(s) found — scale needs "
            f"{MIN_MARKERS_FOR_SCALE}, but the crop (orange box) is still possible"
        )
    else:
        status_text = f"Only {n_found} marker(s) found — not enough to compute scale or crop"

    return pixmap, status_text


