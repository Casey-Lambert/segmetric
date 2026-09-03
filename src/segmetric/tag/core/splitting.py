import os

import cv2
import numpy as np

from .errors import SegMetricError

RENDER_DPI = 1200


def load_first_page(file_path, dpi=RENDER_DPI):
    """Load a file's first page/frame as a BGR numpy array (OpenCV convention).

    PDFs are rendered with PyMuPDF at `dpi`; PNG/JPG files are read directly.
    Raises SegMetricError with a researcher-readable message on failure.
    """
    fname = os.path.basename(file_path)

    if file_path.lower().endswith(".pdf"):
        try:
            import fitz  # PyMuPDF
        except ImportError as exc:
            raise SegMetricError(
                "PyMuPDF is not installed. Install it with 'pip install pymupdf' "
                "and try again."
            ) from exc

        try:
            pdf = fitz.open(file_path)
            if pdf.page_count == 0:
                raise SegMetricError(f"'{fname}' is a PDF with no pages.")
            page = pdf.load_page(0)
            pix = page.get_pixmap(dpi=dpi, alpha=False)
            pdf.close()
            png_bytes = pix.tobytes("png")
            file_bytes = np.frombuffer(png_bytes, np.uint8)
            image = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
        except SegMetricError:
            raise
        except Exception as exc:
            raise SegMetricError(
                f"Could not read '{fname}' — the file may be corrupted or "
                "password-protected."
            ) from exc

        if image is None:
            raise SegMetricError(f"Could not decode a page image from '{fname}'.")
        return image

    image = cv2.imread(file_path)
    if image is None:
        raise SegMetricError(
            f"Could not read '{fname}' as an image — it may be corrupted or in an "
            "unsupported format."
        )
    return image


def split_into_grid(image, rows, cols):
    """Split `image` into a rows x cols grid, row-major, edge-inclusive.

    Matches the notebook's original 4x4 split logic generalized to any grid
    size: each panel is H//rows (W//cols) tall/wide, except the last row/column
    of each which absorbs the remainder so the whole image is covered.

    Returns a list of dicts (in row-major order: row 0 all cols, then row 1, ...)
    with keys: index (1-based), row, col, panel (numpy array), bbox (x1, y1, x2, y2).
    """
    if rows < 1 or cols < 1:
        raise SegMetricError("Rows and columns must both be at least 1.")

    height, width = image.shape[:2]
    step_y = height // rows
    step_x = width // cols

    panels = []
    index = 0
    for row in range(rows):
        y1 = row * step_y
        y2 = (row + 1) * step_y if row < rows - 1 else height
        for col in range(cols):
            x1 = col * step_x
            x2 = (col + 1) * step_x if col < cols - 1 else width
            index += 1
            panels.append(
                {
                    "index": index,
                    "row": row,
                    "col": col,
                    "panel": image[y1:y2, x1:x2],
                    "bbox": (x1, y1, x2, y2),
                }
            )
    return panels
