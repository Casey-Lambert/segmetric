import numpy as np


def measure_cell(cell_mask, mm_per_pixel):
    area_px = int(np.sum(cell_mask > 0))
    area_mm2 = area_px * (mm_per_pixel ** 2)
    coords = np.argwhere(cell_mask > 0)
    if len(coords) == 0:
        return dict(
            area_px=0, area_mm2=0.0, bbox_w_px=0, bbox_h_px=0, bbox_w_mm=0.0, bbox_h_mm=0.0
        )
    r_min, c_min = coords.min(axis=0)
    r_max, c_max = coords.max(axis=0)
    return dict(
        area_px=area_px,
        area_mm2=round(area_mm2, 4),
        bbox_w_px=int(c_max - c_min + 1),
        bbox_h_px=int(r_max - r_min + 1),
        bbox_w_mm=round((c_max - c_min + 1) * mm_per_pixel, 4),
        bbox_h_mm=round((r_max - r_min + 1) * mm_per_pixel, 4),
    )
