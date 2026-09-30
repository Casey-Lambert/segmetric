import csv
import logging
import os
from dataclasses import dataclass, field

import cv2
import numpy as np
from PIL import Image

from segmetric.errors import SegMetricError
from segmetric.tag.core.discovery import find_input_files
from segmetric.tag.core.naming import DEFAULT_OUTPUT_FORMAT, OUTPUT_FORMAT_EXTENSIONS

from .cropping import crop_region_from_settings, crop_to_markers
from .detection import build_detector, build_prepare_detector
from .manual import crop_to_region
from .model import ScaleSettings
from .preparation import MIN_MARKERS_FOR_PREPARE, prepare_image
from .scale import compute_image_scale

SCALE_SUBDIR = "scale"
CSV_FILENAME = "scales.csv"

SCALE_SOURCE_MEASURED = "measured"
SCALE_SOURCE_BATCH_MEDIAN = "batch_median"
SCALE_SOURCE_PAGE_MEDIAN = "page_median"
SCALE_SOURCE_MANUAL = "manual"
SCALE_SOURCE_MANUAL_BATCH = "manual_batch"


@dataclass
class ScaleJobResult:
    output_dir: str
    files_processed: list = field(default_factory=list)  #  cropped
    files_skipped: list = field(default_factory=list)  # (file_name, reason)
    scale_rows: list = field(default_factory=list)  # (file_name, mm_per_pixel, scale_source)
    panels_cropped: int = 0
    interrupted: bool = False


def _make_output_dir(output_folder):
    scale_dir = os.path.join(output_folder, SCALE_SUBDIR)
    try:
        os.makedirs(scale_dir, exist_ok=True)
    except OSError as exc:
        raise SegMetricError(
            f"Could not create the output folder '{scale_dir}': {exc.strerror}."
        ) from exc
    return scale_dir


def _make_logger(scale_dir):
    logger = logging.getLogger(f"segmetric.scale.pipeline.{id(scale_dir)}")
    logger.setLevel(logging.ERROR)
    logger.propagate = False
    handler = logging.FileHandler(os.path.join(scale_dir, "segmetric_scale.log"))
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.handlers = [handler]
    return logger


def _save_cropped(image_bgr, out_path):
    Image.fromarray(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)).save(
        out_path, dpi=(1200, 1200)
    )


def _write_csv(scale_dir, scale_rows):
    csv_path = os.path.join(scale_dir, CSV_FILENAME)
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["file_name", "mm_per_pixel", "scale_source"])
        for file_name, mm_per_pixel, source in scale_rows:
            writer.writerow([file_name, mm_per_pixel, source])
    return csv_path


def _apply_median_fallback(readable_files, valid_scales, failed_names, scale_by_name, group_size, report):
    """Fill scale_by_name for every name in failed_names, then return the
    (file_name, mm_per_pixel, scale_source) rows for every file, in
    sequence."""
    failed_set = set(failed_names)

    if not group_size or group_size < 1:
        batch_median = float(np.median(valid_scales))
        for file_name in failed_names:
            scale_by_name[file_name] = batch_median
        report(
            0.5,
            f"Batch median scale: {batch_median:.6f} mm/px "
            f"({len(valid_scales)} measured, {len(failed_names)} using the median).",
        )
        return [
            (
                file_name,
                scale_by_name[file_name],
                SCALE_SOURCE_BATCH_MEDIAN if file_name in failed_set else SCALE_SOURCE_MEASURED,
            )
            for file_name, _ in readable_files
        ]

    # Grouped fallback.
    whole_batch_median = float(np.median(valid_scales))
    source_by_name = {}
    n_groups = 0
    n_page_fallback = 0
    n_batch_fallback = 0

    for start in range(0, len(readable_files), group_size):
        n_groups += 1
        group_names = [name for name, _ in readable_files[start:start + group_size]]
        group_valid = [scale_by_name[name] for name in group_names if name not in failed_set]
        group_median = float(np.median(group_valid)) if group_valid else whole_batch_median

        for name in group_names:
            if name not in failed_set:
                source_by_name[name] = SCALE_SOURCE_MEASURED
                continue
            scale_by_name[name] = group_median
            if group_valid:
                source_by_name[name] = SCALE_SOURCE_PAGE_MEDIAN
                n_page_fallback += 1
            else:
                source_by_name[name] = SCALE_SOURCE_BATCH_MEDIAN
                n_batch_fallback += 1

    report(
        0.5,
        f"Computed per-page median scale across {n_groups} page(s) of "
        f"{group_size} panel(s) each ({len(valid_scales)} measured, "
        f"{n_page_fallback} using their page's median, {n_batch_fallback} "
        "using the whole-batch median as a last resort).",
    )

    return [
        (file_name, scale_by_name[file_name], source_by_name[file_name])
        for file_name, _ in readable_files
    ]


def run_scale_job(
    input_folder,
    output_folder,
    settings: ScaleSettings = ScaleSettings(),
    progress_cb=None,
    should_stop=None,
    group_size=None,
    output_format=DEFAULT_OUTPUT_FORMAT,
):

    input_files = find_input_files(input_folder)
    scale_dir = _make_output_dir(output_folder)
    logger = _make_logger(scale_dir)
    detector = build_detector(settings)
    prepare_detector = build_prepare_detector(settings)

    result = ScaleJobResult(output_dir=scale_dir)

    def stop_requested():
        return should_stop is not None and should_stop()

    def report(fraction, message):
        if progress_cb is not None:
            progress_cb(fraction, message)

    total_files = len(input_files)
    report(0.0, f"Found {total_files} file(s) in {input_folder}.")

    # ---------------------------------------------------------------- first pass 
    valid_scales = []
    scale_by_name = {}
    failed_names = []
    readable_files = []  # (file_name, file_path)

    for i, file_path in enumerate(input_files, start=1):
        file_name = os.path.basename(file_path)
        if stop_requested():
            result.interrupted = True
            break

        report(
            (i - 1) / total_files / 2,
            f"Pass 1/2 — scale {i} of {total_files}: {file_name}",
        )

        image = cv2.imread(file_path)
        if image is None:
            logger.error("Could not read %s", file_name)
            result.files_skipped.append((file_name, "Could not read the image."))
            continue

        prepared = prepare_image(
            image,
            prepare_detector,
            use_blob_fallback=settings.use_blob_fallback,
            blob_min_area=settings.prepare_blob_min_area,
            blob_max_area=settings.prepare_blob_max_area,
            blob_min_aspect=settings.blob_min_aspect,
            blob_max_aspect=settings.blob_max_aspect,
        )
        if prepared is None:
            logger.error("Not enough markers to prepare %s", file_name)
            result.files_skipped.append(
                (
                    file_name,
                    f"Not enough markers to prepare the image (needs at least "
                    f"{MIN_MARKERS_FOR_PREPARE}).",
                )
            )
            continue

        readable_files.append((file_name, file_path))
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
        if mm_per_pixel is None:
            failed_names.append(file_name)
        else:
            valid_scales.append(mm_per_pixel)
            scale_by_name[file_name] = mm_per_pixel

    if not valid_scales:
        if result.interrupted:
            report(0.5, "Stopped during scale detection — no scales computed yet.")
            return result
        raise SegMetricError(
            "No image had enough ArUco markers to compute a "
            "scale. Check the input folder or threshold settings."
        )

    #safe gaurd to still build csv
    scale_rows = _apply_median_fallback(
        readable_files, valid_scales, failed_names, scale_by_name, group_size, report
    )

    if result.interrupted:
        result.scale_rows = scale_rows
        csv_path = _write_csv(scale_dir, scale_rows)
        report(0.5, f"Stopped — scales for {len(scale_rows)} file(s) saved to {csv_path}.")
        return result

    # -------------------------------------------------------------- step 2 
    
    
    panels_cropped = 0
    total_readable = len(readable_files)

    for i, (file_name, file_path) in enumerate(readable_files, start=1):
        if stop_requested():
            result.interrupted = True
            break

        report(
            0.5 + (i - 1) / total_readable / 2,
            f"Pass 2/2 — crop {i} of {total_readable}: {file_name}",
        )

        image = cv2.imread(file_path)
        if image is None:
            continue  

        prepared = prepare_image(
            image,
            prepare_detector,
            use_blob_fallback=settings.use_blob_fallback,
            blob_min_area=settings.prepare_blob_min_area,
            blob_max_area=settings.prepare_blob_max_area,
            blob_min_aspect=settings.blob_min_aspect,
            blob_max_aspect=settings.blob_max_aspect,
        )
        if prepared is None:
            continue  

        cropped = crop_to_markers(
            prepared,
            detector,
            region=crop_region_from_settings(settings),
            use_blob_fallback=settings.use_blob_fallback,
            blob_min_area=settings.final_blob_min_area,
            blob_max_area=settings.final_blob_max_area,
            blob_min_aspect=settings.blob_min_aspect,
            blob_max_aspect=settings.blob_max_aspect,
        )
        if cropped is None:
            logger.error("Not enough markers to crop %s", file_name)
            result.files_skipped.append((file_name, "Not enough markers to crop."))
            continue

        ext = OUTPUT_FORMAT_EXTENSIONS[output_format]
        out_name = f"{os.path.splitext(file_name)[0]}_cropped.{ext}"
        _save_cropped(cropped, os.path.join(scale_dir, out_name))
        panels_cropped += 1
        result.files_processed.append(file_name)

    result.panels_cropped = panels_cropped
    result.scale_rows = scale_rows
    csv_path = _write_csv(scale_dir, scale_rows)

    if result.interrupted:
        report(
            1.0,
            f"Stopped — {panels_cropped} image(s) cropped, scales for "
            f"{len(scale_rows)} file(s) saved to {csv_path}.",
        )
    else:
        report(1.0, f"Done — {panels_cropped} image(s) cropped, scales saved to {csv_path}.")

    return result


def run_manual_scale_job(
    input_folder,
    output_folder,
    scale_by_name,
    scale_source_by_name,
    crop_bbox_by_name,
    progress_cb=None,
    should_stop=None,
    output_format=DEFAULT_OUTPUT_FORMAT,
):
   
    input_files = find_input_files(input_folder)
    scale_dir = _make_output_dir(output_folder)

    result = ScaleJobResult(output_dir=scale_dir)

    def stop_requested():
        return should_stop is not None and should_stop()

    def report(fraction, message):
        if progress_cb is not None:
            progress_cb(fraction, message)

    total_files = len(input_files)
    report(0.0, f"Found {total_files} file(s) in {input_folder}.")

    scale_rows = []
    ext = OUTPUT_FORMAT_EXTENSIONS[output_format]

    for i, file_path in enumerate(input_files, start=1):
        file_name = os.path.basename(file_path)
        if stop_requested():
            result.interrupted = True
            break

        report((i - 1) / total_files, f"Processing {i} of {total_files}: {file_name}")

        if file_name not in scale_by_name:
            result.files_skipped.append((file_name, "No manual scale was set for this file."))
            continue

        image = cv2.imread(file_path)
        if image is None:
            result.files_skipped.append((file_name, "Could not read the image."))
            continue

        if crop_bbox_by_name is not None:
            bbox = crop_bbox_by_name.get(file_name)
            if bbox is None:
                result.files_skipped.append((file_name, "No manual crop region was set for this file."))
                continue
            height, width = image.shape[:2]
            x1, y1, x2, y2 = bbox
            x1, y1, x2, y2 = max(0, min(x1, width)), max(0, min(y1, height)), max(0, min(x2, width)), max(0, min(y2, height))
            output_image = crop_to_region(image, (x1, y1, x2, y2))
        else:
            output_image = image

        out_name = f"{os.path.splitext(file_name)[0]}_cropped.{ext}"
        _save_cropped(output_image, os.path.join(scale_dir, out_name))
        result.files_processed.append(file_name)
        scale_rows.append((file_name, scale_by_name[file_name], scale_source_by_name.get(file_name, SCALE_SOURCE_MANUAL)))

    result.panels_cropped = len(result.files_processed)
    result.scale_rows = scale_rows
    csv_path = _write_csv(scale_dir, scale_rows)

    if result.interrupted:
        report(
            len(result.files_processed) / max(total_files, 1),
            f"Stopped — {result.panels_cropped} image(s) saved, scales for "
            f"{len(scale_rows)} file(s) saved to {csv_path}.",
        )
    else:
        report(1.0, f"Done — {result.panels_cropped} image(s) saved, scales saved to {csv_path}.")

    return result
