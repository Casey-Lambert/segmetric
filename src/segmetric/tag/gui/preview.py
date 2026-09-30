

import cv2
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QPixmap

from ..core.naming import OcrRegion, compute_search_bbox
from ..core.splitting import load_first_page, split_into_grid

PREVIEW_DPI = 200 #change if you need more detail in preview 


def load_preview_page(file_path, dpi=PREVIEW_DPI):
    """Load a file's first page at a lower DPI, fast enough for on-screen preview."""
    return load_first_page(file_path, dpi=dpi)


def bgr_to_qpixmap(image_bgr):
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    rgb = rgb.copy()  # own the buffer so QImage doesn't reference freed memory
    height, width, _ = rgb.shape
    bytes_per_line = 3 * width
    qimage = QImage(
        rgb.data, width, height, bytes_per_line, QImage.Format.Format_RGB888
    )
    return QPixmap.fromImage(qimage.copy())


def render_grid_preview(image_bgr, rows, cols, ocr_region: OcrRegion = None):
    """Return a QPixmap of image_bgr with rows x cols grid lines drawn over it.
    Lets you se the split before running it - can adjust if there is need 
    """
    panels = split_into_grid(image_bgr, rows, cols)
    pixmap = bgr_to_qpixmap(image_bgr)

    painter = QPainter(pixmap)
    grid_pen = QPen(QColor(255, 40, 40))
    grid_pen.setWidth(max(2, pixmap.width() // 400))
    painter.setPen(grid_pen)
    for panel_info in panels:
        x1, y1, x2, y2 = panel_info["bbox"]
        painter.drawRect(x1, y1, x2 - x1, y2 - y1)

    if ocr_region is not None:
        highlight_fill = QColor(255, 165, 0, 90)
        highlight_pen = QPen(QColor(255, 140, 0))
        highlight_pen.setWidth(max(2, pixmap.width() // 400))
        painter.setPen(highlight_pen)
        painter.setBrush(highlight_fill)
        for panel_info in panels:
            px1, py1, _, _ = panel_info["bbox"]
            panel = panel_info["panel"]
            rx1, ry1, rx2, ry2 = compute_search_bbox(panel.shape, ocr_region)
            painter.drawRect(px1 +  rx1, py1 + ry1, rx2 - rx1, ry2 - ry1)

    painter.end()
    return pixmap






