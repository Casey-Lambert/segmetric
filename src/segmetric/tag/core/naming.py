import re
import threading
from dataclasses import dataclass

from .errors import SegMetricError

_reader_lock = threading.Lock()
_cached_readers = {}  # {gpu: easyocr.Reader}

# Matches the notebook's original hardcoded OCR crop: bottom half, full width.
DEFAULT_V_ANCHOR = "bottom"
DEFAULT_V_SIZE_PCT = 50
DEFAULT_H_ANCHOR = "left"
DEFAULT_H_SIZE_PCT = 100


@dataclass(frozen=True)
class OcrRegion:
    """Where within a panel to search for text, as percentages of panel size.

    v_anchor/h_anchor pick which edge the band is measured from ("top"/"bottom"
    and "left"/"right"); v_size_pct/h_size_pct control how much of the panel's
    height/width that band covers, growing or shrinking from that edge.
    """

    v_anchor: str = DEFAULT_V_ANCHOR
    v_size_pct: int = DEFAULT_V_SIZE_PCT
    h_anchor: str = DEFAULT_H_ANCHOR
    h_size_pct: int = DEFAULT_H_SIZE_PCT


def compute_search_bbox(panel_shape, region: OcrRegion):
    """Return the (x1, y1, x2, y2) pixel box `region` describes within a panel
    of shape `panel_shape` (as from a numpy array's .shape).
    """
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


# TIFF is the default output format (better for downstream measurement work
# than a lossy/compressed format); PNG and JPEG are offered as alternatives.
DEFAULT_OUTPUT_FORMAT = "tiff"
OUTPUT_FORMAT_EXTENSIONS = {
    "tiff": "tiff",
    "png": "png",
    "jpeg": "jpg",
}


def sequential_filename(index, run_id, output_format=DEFAULT_OUTPUT_FORMAT):
    """Matches the notebook's default naming: panel_XX_<run_id>.<ext>."""
    ext = OUTPUT_FORMAT_EXTENSIONS[output_format]
    return f"panel_{index:02d}_{run_id}.{ext}"


def sanitize_ocr_text(raw_text):
    """Clean raw OCR text into a filename-safe label (notebook Cell 5 logic).

    Returns "" if nothing usable remains.
    """
    label = raw_text.strip().replace(" ", "_")
    label = label.replace("I", "1")  # OCR often misreads 1 as I
    label = re.sub(r"[^A-Za-z0-9_\-]", "", label)
    label = re.sub(r"_+", "_", label)
    return label.strip("_")


def get_ocr_reader(gpu=True):
    """Lazily create and cache a shared easyocr.Reader for the given engine.

    gpu defaults to True, matching the notebook's original hardcoded setting.
    easyocr itself falls back to CPU with a warning if no GPU is available, so
    this is safe on machines without CUDA (e.g. Mac) -- it just won't be fast.
    Readers are cached per gpu/cpu choice so switching the setting between
    runs doesn't silently keep reusing the other engine.
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
    """Run OCR on `region` of a panel image and return a sanitized label.

    Returns "" if OCR found no usable text (caller decides on a fallback name).
    """
    x1, y1, x2, y2 = compute_search_bbox(panel_bgr.shape, region)
    search_area = panel_bgr[y1:y2, x1:x2]
    result = reader.readtext(search_area, detail=0)
    return sanitize_ocr_text(" ".join(result))


def cv_filename(index, run_id, label, output_format=DEFAULT_OUTPUT_FORMAT):
    """Build a CV-naming output filename, matching the notebook's Cell 5 scheme.

    Falls back to '<panel_XX>_RENAME_ME_pXX_<run_id>.<ext>' when label is empty,
    same as the notebook, so unreadable panels are easy to spot and hand-rename.
    """
    ext = OUTPUT_FORMAT_EXTENSIONS[output_format]
    if not label:
        label = f"panel_{index:02d}_RENAME_ME"
    return f"{label}_p{index:02d}_{run_id}.{ext}"
