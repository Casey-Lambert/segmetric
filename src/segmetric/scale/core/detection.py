import cv2
import numpy as np

from .model import (
    DEFAULT_BLOB_MAX_ASPECT,
    DEFAULT_BLOB_MIN_ASPECT,
    DEFAULT_FINAL_BLOB_MAX_AREA,
    DEFAULT_FINAL_BLOB_MIN_AREA,
    DEFAULT_PREPARE_BLOB_MAX_AREA,
    DEFAULT_PREPARE_BLOB_MIN_AREA,
    ScaleSettings,
)

#
MIN_MARKER_PERIMETER_RATE = 0.01
MAX_MARKER_PERIMETER_RATE = 0.60
POLYGONAL_APPROX_ACCURACY_RATE = 0.03
CORNER_REFINEMENT_WIN_SIZE = 5
CORNER_REFINEMENT_MAX_ITERATIONS = 50
CORNER_REFINEMENT_MIN_ACCURACY = 0.01

# Blob-fallback trigger: ArUco must find fewer than ## markers
BLOB_MIN_MARKERS_TO_TRIGGER = 4


BLOB_MIN_AREA = DEFAULT_FINAL_BLOB_MIN_AREA
BLOB_MAX_AREA = DEFAULT_FINAL_BLOB_MAX_AREA
BLOB_MIN_ASPECT = DEFAULT_BLOB_MIN_ASPECT
BLOB_MAX_ASPECT = DEFAULT_BLOB_MAX_ASPECT


PREPARE_BLOB_MIN_AREA = DEFAULT_PREPARE_BLOB_MIN_AREA
PREPARE_BLOB_MAX_AREA = DEFAULT_PREPARE_BLOB_MAX_AREA


def build_detector(settings: ScaleSettings = ScaleSettings()):
    
    parameters = cv2.aruco.DetectorParameters()
    parameters.adaptiveThreshConstant = settings.adaptive_thresh_constant
    parameters.adaptiveThreshWinSizeMin = settings.adaptive_thresh_win_size_min
    parameters.adaptiveThreshWinSizeMax = settings.adaptive_thresh_win_size_max
    parameters.adaptiveThreshWinSizeStep = settings.adaptive_thresh_win_size_step
    parameters.minMarkerPerimeterRate = MIN_MARKER_PERIMETER_RATE
    parameters.maxMarkerPerimeterRate = MAX_MARKER_PERIMETER_RATE
    parameters.polygonalApproxAccuracyRate = POLYGONAL_APPROX_ACCURACY_RATE
    parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    parameters.cornerRefinementWinSize = CORNER_REFINEMENT_WIN_SIZE
    parameters.cornerRefinementMaxIterations = CORNER_REFINEMENT_MAX_ITERATIONS
    parameters.cornerRefinementMinAccuracy = CORNER_REFINEMENT_MIN_ACCURACY

    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    return cv2.aruco.ArucoDetector(aruco_dict, parameters)


def build_prepare_detector(settings: ScaleSettings = ScaleSettings()):
    
    parameters = cv2.aruco.DetectorParameters()
    parameters.adaptiveThreshConstant = settings.adaptive_thresh_constant
    parameters.adaptiveThreshWinSizeMin = settings.adaptive_thresh_win_size_min
    parameters.adaptiveThreshWinSizeMax = settings.prepare_win_size_max
    parameters.adaptiveThreshWinSizeStep = settings.prepare_win_size_step
    parameters.minMarkerPerimeterRate = MIN_MARKER_PERIMETER_RATE
    parameters.maxMarkerPerimeterRate = MAX_MARKER_PERIMETER_RATE
    parameters.polygonalApproxAccuracyRate = POLYGONAL_APPROX_ACCURACY_RATE
    parameters.errorCorrectionRate = settings.prepare_error_correction_rate
    parameters.perspectiveRemovePixelPerCell = settings.prepare_perspective_remove_pixel_per_cell
    parameters.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
    parameters.cornerRefinementWinSize = CORNER_REFINEMENT_WIN_SIZE
    parameters.cornerRefinementMaxIterations = CORNER_REFINEMENT_MAX_ITERATIONS
    parameters.cornerRefinementMinAccuracy = CORNER_REFINEMENT_MIN_ACCURACY

    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    return cv2.aruco.ArucoDetector(aruco_dict, parameters)


def _blob_fallback(
    gray,
    corners,
    ids,
    min_area=BLOB_MIN_AREA,
    max_area=BLOB_MAX_AREA,
    min_aspect=BLOB_MIN_ASPECT,
    max_aspect=BLOB_MAX_ASPECT,
):
 
    if ids is not None and len(ids) >= BLOB_MIN_MARKERS_TO_TRIGGER:
        return corners, ids

    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    blobs = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if not (min_area < area < max_area):
            continue
        x, y, w, h = cv2.boundingRect(contour)
        if not (min_aspect < w / h < max_aspect):
            continue
        blobs.append((area, x, y, w, h))

    blobs.sort(reverse=True)
    blobs = blobs[:4]
    if len(blobs) < 4:
        return corners, ids

    blob_corners = [
        np.array(
            [[x, y], [x + w, y], [x + w, y + h], [x, y + h]], dtype=np.float32
        ).reshape(1, 4, 2)
        for _, x, y, w, h in blobs
    ]
    blob_ids = np.arange(len(blobs), dtype=np.int32).reshape(-1, 1)
    return blob_corners, blob_ids


def detect_markers(
    image_bgr,
    detector,
    use_blob_fallback=True,
    blob_min_area=BLOB_MIN_AREA,
    blob_max_area=BLOB_MAX_AREA,
    blob_min_aspect=BLOB_MIN_ASPECT,
    blob_max_aspect=BLOB_MAX_ASPECT,
):
    """Detect ArUco markers on the grayscale of image_bgr, optionally
    falling back to blob detection """
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    corners, ids, _ = detector.detectMarkers(gray)
    if use_blob_fallback:
        corners, ids = _blob_fallback(
            gray, corners, ids, blob_min_area, blob_max_area, blob_min_aspect, blob_max_aspect
        )
    return corners, ids


def compute_marker_centers(corners):
    """Return an (N, 2) float32 array ofß center points."""
    centers = [c.reshape((4, 2)).mean(axis=0) for c in corners]
    return np.array(centers, dtype=np.float32)
