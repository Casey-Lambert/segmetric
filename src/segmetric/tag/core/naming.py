import re
import threading
from dataclasses import dataclass

from .errors import SegMetricError

_reader_lock = threading.Lock()
_cached_readers = {}  # {gpu: easyocr.Reader}

# Can hard code/ preset this by changing these numbers
DEFAULT_V_ANCHOR = "bottom"
DEFAULT_V_SIZE_PCT = 50
DEFAULT_H_ANCHOR = "left"
DEFAULT_H_SIZE_PCT = 100


@dataclass(frozen=True)
class OcrRegion:
    """Where within a panel to search for text, as p% of panel size."""

    v_anchor: str = DEFAULT_V_ANCHOR
    v_size_pct: int = DEFAULT_V_SIZE_PCT
    h_anchor: str = DEFAULT_H_ANCHOR
    h_size_pct: int = DEFAULT_H_SIZE_PCT


def compute_search_bbox(panel_shape, region: OcrRegion):
    """Return the (x1, y1, x2, y2) pixel box ( numpy array -  .shape)"""
    height, width = panel_shape[:2]
    band_h = min(height, max(1, round(height * region.v_size_pct / 100)))
    band_w = min(width, max(1, round(width * region.h_size_pct / 100)))

    if region.v_anchor == "top":
        y1, y2 = 0, band_h
    else:
        y1, y2 = height - band_h, height

    if region.h_anchor == "left":
        x1, x2 = 0, band_w
    else:
        x1, x2 = width - band_w, width

    return x1, y1, x2, y2


# TIFF default output- it preserves the image quality, avoids compression

DEFAULT_OUTPUT_FORMAT = "tiff"
OUTPUT_FORMAT_EXTENSIONS = {
    "tiff": "tiff",
    "png": "png",
    "jpeg": "jpg",
}


def sequential_filename(index, run_id, output_format=DEFAULT_OUTPUT_FORMAT):
    ext = OUTPUT_FORMAT_EXTENSIONS[output_format]
    return f"panel_{index:02d}_{run_id}.{ext}"

### CHANGE TO MEET REQUIREMENTS
#-----------------------------------------------------------------correct  
def sanitize_ocr_text(raw_text):
    label = raw_text.strip().replace(" ", "_")
    label = label.replace("I", "1")  # OCR often misreads 1 as I
    label = re.sub(r"[^A-Za-z0-9_\-]", "", label)
    label = re.sub(r"_+", "_", label)
    return label.strip("_")


def get_ocr_reader(gpu=True):
    """create and cache a shared easyocr.Reader. CPU/GPU options
    """
    with _reader_lock:
        if gpu not in _cached_readers:
            try:
                import easyocr
            except ImportError as exc:
                raise SegMetricError(
                    "Computer-vision naming requires the 'easyocr' package. "
                    "Install it with 'pip install easyocr' and try again."
                ) from exc
            try:
                _cached_readers[gpu] = easyocr.Reader(["en"], gpu=gpu)
            except Exception as exc:
                raise SegMetricError(
                    "Could not initialize the OCR engine. See the log file for "
                    "details."
                ) from exc
        return _cached_readers[gpu]




def ocr_label_for_panel(panel_bgr, reader, region: OcrRegion = OcrRegion()):
    """Run OCR on `region` of a panel image and return a label."""
    x1, y1, x2, y2 = compute_search_bbox(panel_bgr.shape, region)
    search_area = panel_bgr[y1:y2, x1:x2]
    result = reader.readtext(search_area, detail=0)
    return sanitize_ocr_text(" ".join(result))


def cv_filename(index, run_id, label, output_format=DEFAULT_OUTPUT_FORMAT):
    """Build a CV-naming output filename, matching the notebook's Cell 5 scheme.
    """
    ext = OUTPUT_FORMAT_EXTENSIONS[output_format]
    if not label:
        label = f"panel_{index:02d}_RENAME_ME"
    return f"{label}_p{index:02d}_{run_id}.{ext}"



