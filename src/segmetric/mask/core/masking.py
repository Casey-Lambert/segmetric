
import cv2
import numpy as np

from .model import FilterSettings

# Fourier smoothing only kicks in above set number of contour points (see line below)

MIN_CONTOUR_POINTS_FOR_SMOOTHING = 200 #<-can change number of contor points


def _smooth_contour_fourier(contour, keep_freq):
    """Low-pass contour filter (x, y) coordinates with FFT, keeping only
    the lowest keep_freq fraction of frequencies (minumum of 10 components).
    .
    """
    pts = contour[:, 0, :].astype(np.float32)
    pts_complex = pts[:, 0] + 1j * pts[:, 1]
    fft = np.fft.fft(pts_complex)
    n = len(fft)
    cutoff = max(int(n * keep_freq), 10)
    fft_filtered = np.zeros_like(fft)
    fft_filtered[:cutoff] = fft[:cutoff]
    fft_filtered[-cutoff:] = fft[-cutoff:]
    pts_smooth = np.fft.ifft(fft_filtered)
    x = np.real(pts_smooth).astype(np.int32)
    y = np.imag(pts_smooth).astype(np.int32)
    return np.stack([x, y], axis=1).reshape((-1, 1, 2))


def generate_mask(image_bgr, filter_settings: FilterSettings):
    """Generate a binary object mask from image_bgr using filter_settings'
    parameters (7). 
    First pass; flow to locate the blob in the image: LAB chroma + inverted-L "signal" -> two-pass Otsu threshold 
    Second pass; largest blob component above min_blob size -> morph kernal close ->
    flood-fill -> smoothed outer contour.

    Returns a uint8 mask (values 0/1), the same shape as image_bgr's.
    """
    p = filter_settings
    img_lab = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2LAB)
    L, a, b = cv2.split(img_lab)

    a_c = a.astype(np.float32) - 128
    b_c = b.astype(np.float32) - 128
    chroma = np.sqrt(a_c ** 2 + b_c ** 2)
    chroma_max = max(float(chroma.max()), 1e-6)  # guard a blank/flat crop
    chroma_norm = (chroma / chroma_max * 255).astype(np.uint8)
    L_inv = (255 - L).astype(np.uint8)
    signal = cv2.addWeighted(chroma_norm, 0.70, L_inv, 0.30, 0)

    otsu_val, _ = cv2.threshold(signal, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    _, binary_first = cv2.threshold(
        signal, int(otsu_val * p.first_pass_factor), 255, cv2.THRESH_BINARY
    )

    num_labels, labels_im = cv2.connectedComponents(binary_first.astype(np.uint8))
    max_area, best_label = 0, 1
    for label in range(1, num_labels):
        area = np.sum(labels_im == label)
        if area > max_area:
            max_area = area
            best_label = label

    h, w = signal.shape
    first_pass_object = labels_im == best_label

    erode_kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (max(1, p.erode_px), max(1, p.erode_px))
    )
    first_pass_interior = cv2.erode(
        first_pass_object.astype(np.uint8), erode_kernel
    ).astype(bool)

    interior_l_values = L[first_pass_interior]
    if interior_l_values.size == 0:
        dark_vein_map = np.zeros((h, w), dtype=bool)
    else:
        dark_cutoff = np.percentile(interior_l_values, 10)
        dark_vein_map = first_pass_interior & (L <= dark_cutoff)

    threshold_map = np.full((h, w), otsu_val * p.normal_thresh, dtype=np.float32)
    threshold_map[dark_vein_map] = otsu_val * p.vein_thresh

    binary = (signal.astype(np.float32) > threshold_map).astype(np.uint8) * 255

    num_labels, labels_im = cv2.connectedComponents(binary)
    max_area = 0
    object_mask = np.zeros_like(binary)
    for label in range(1, num_labels):
        component = (labels_im == label).astype(np.uint8)
        area = np.sum(component)
        if area > max_area and area > p.min_blob:
            max_area = area
            object_mask = component

    kernel_close = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE, (max(1, p.close_px), max(1, p.close_px))
    )
    mask_closed = cv2.morphologyEx(object_mask, cv2.MORPH_CLOSE, kernel_close)

    mask_filled = mask_closed.copy()
    flood_seed = np.zeros((h + 2, w + 2), np.uint8)
    cv2.floodFill(mask_filled, flood_seed, (0, 0), 255)
    mask_filled = cv2.bitwise_not(mask_filled)
    mask_filled = cv2.bitwise_or(mask_closed * 255, mask_filled)
    mask_filled = (mask_filled > 0).astype(np.uint8)

    contours, _ = cv2.findContours(
        (mask_filled * 255).astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE
    )
    mask_smooth = np.zeros_like(mask_filled)
    if contours:
        largest = max(contours, key=cv2.contourArea)
        if len(largest) > MIN_CONTOUR_POINTS_FOR_SMOOTHING:
            smoothed = _smooth_contour_fourier(largest, keep_freq=p.fourier_freq)
        else:
            smoothed = largest
        cv2.drawContours(mask_smooth, [smoothed], -1, 1, thickness=-1)

    return mask_smooth
