import cv2
import numpy as np
from scipy import ndimage as ndi
from skimage.filters import sato, threshold_local
from skimage.morphology import h_maxima, remove_small_objects
from skimage.segmentation import watershed

from .model import DetectionSettings


def segment_cells(img_rgb, wing_mask, settings: DetectionSettings = DetectionSettings()):
    """Detect candidate cell regions inside wing_mask: a Sato vein-ridge
    filter locates veins, watershed (seeded by distance-transform maxima)
    fills the space between them into labeled candidate cells. Direct port
    of the notebooks' segment_cells(), with all 8 previously-hardcoded
    constants exposed via `settings`.

    wing_mask is uint8 (0/1) -- pass an all-ones array the size of img_rgb
    to segment the whole image (the notebooks' own "no wing mask" fallback).

    Note: local_thresh_block_size must be odd (skimage's own requirement).

    Returns (labeled, n_cells, vein_mask): labeled is an int array of the
    same shape as wing_mask (0 = background, 1..n_cells = candidate cell
    regions); vein_mask is a uint8 (0/255) visualization of the detected
    veins.
    """
    img_gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
    veins = sato(
        img_gray, sigmas=(settings.sato_sigma_min, settings.sato_sigma_max), black_ridges=True
    )
    local_thresh = threshold_local(
        veins, block_size=settings.local_thresh_block_size, offset=settings.local_thresh_offset
    )
    binary_veins = veins > local_thresh
    binary_veins[wing_mask == 0] = 0

    kernel = np.ones((settings.vein_close_px, settings.vein_close_px), np.uint8)
    binary_veins = cv2.morphologyEx(binary_veins.astype(np.uint8), cv2.MORPH_CLOSE, kernel)
    binary_veins = remove_small_objects(binary_veins.astype(bool), min_size=settings.min_vein_size)

    dist = ndi.distance_transform_edt(~binary_veins & (wing_mask > 0))
    dist = ndi.gaussian_filter(dist, sigma=settings.distance_gaussian_sigma)
    dist_suppressed = h_maxima(dist, h=settings.h_maxima_h)
    markers, _ = ndi.label(dist_suppressed)
    labeled = watershed(-dist, markers, mask=wing_mask)

    return labeled, int(labeled.max()), (binary_veins * 255).astype(np.uint8)
