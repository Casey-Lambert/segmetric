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
    files_processed: list = field(default_factory=list)  # successfully cropped
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
    (file_name, mm_per_pixel, scale_source) rows for every readable file, in
    order.

    group_size=None (or < 1): one flat median across the whole batch --
    the notebook's original, unchanged behavior.

    group_size=N: readable_files is chunked into consecutive blocks of N
    (matching how a caller like segmetric.prepare numbers panels
    sequentially per source page: N = rows * cols). Each failed image is
    backfilled with its OWN group's median instead of the whole batch's. A
    group with zero valid measurements of its own falls back to the
    whole-batch median as a last resort -- flagged 'batch_median', same
    label as the ungrouped case; a normal per-page fallback is flagged
    'page_median' so the two are distinguishable in the CSV.
    """
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

    # Grouped (per-page) fallback.
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
    """Two-pass ArUco scale + crop batch job, matching the notebook's Cell 9
    -- preceded by the notebook's Cell 7 preparation step (see
    preparation.prepare_image): each image is first cropped tight to its
    markers and upscaled 2x before either pass runs, so the measured scale
    and the saved cropped image are both calibrated to that same pixel
    space, matching how the notebook's Cell 9 actually operated on Cell 7's
    output (Prepared_Crops) rather than on raw split panels. Images with
    fewer than 3 markers can't be prepared at all and are skipped entirely
    (no scale, no crop) -- flagged in files_skipped.

    Pass 1 -- for each preparable image, detect markers and compute mm/pixel
    (needs >=4 markers). Images that don't have enough markers are
    backfilled with a median of other successfully-measured images and
    flagged accordingly in the CSV (vs. 'measured'), so the fallback is
    visible instead of silent:

    - group_size=None (default): one median across the *whole batch* --
      exactly the notebook's original fallback -- flagged 'batch_median'.
      This is what standalone segmetric-scale always uses.
    - group_size=N: the batch is chunked into consecutive groups of N
      images (e.g. N = rows * cols for panels split from same-sized source
      pages, as segmetric.prepare uses), and each failed image is
      backfilled from its *own group's* median instead -- flagged
      'page_median'. If a whole group has no valid measurements of its
      own, it falls back to the whole-batch median as a last resort,
      still flagged 'batch_median' for that image.

    Pass 2 -- for each prepared image, detect markers again (looser
    requirement: >=2) and crop to the marker bounding box, saving the
    result to <output_folder>/scale/ as output_format (tiff/png/jpeg,
    default tiff -- matching segmetric.tag's panel output).

    should_stop, if given, is checked between files in both passes.
    Stopping during pass 1 skips pass 2 entirely (there's no complete scale
    picture yet to crop against) and writes a CSV of whatever was computed
    so far. Stopping during pass 2 still writes the CSV for every file
    (pass 1 always finishes first) but crops fewer images.
    """
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

    # ---------------------------------------------------------------- pass 1
    valid_scales = []
    scale_by_name = {}
    failed_names = []
    readable_files = []  # (file_name, file_path) read AND prepared successfully in pass 1

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
            "No image in this batch had enough ArUco markers to compute a "
            "scale, so there's nothing to fall back to. Check the input "
            "folder or the threshold settings."
        )

    # Scale is now known for every readable file, measured or backfilled --
    # build the CSV rows now so they're complete even if pass 2 stops early.
    scale_rows = _apply_median_fallback(
        readable_files, valid_scales, failed_names, scale_by_name, group_size, report
    )

    if result.interrupted:
        result.scale_rows = scale_rows
        csv_path = _write_csv(scale_dir, scale_rows)
        report(0.5, f"Stopped — scales for {len(scale_rows)} file(s) saved to {csv_path}.")
        return result

    # ---------------------------------------------------------------- pass 2
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
            continue  # already flagged as skipped in pass 1

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
            continue  # pass 1 already verified this file prepares; defensive only

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
    """The no-marker counterpart to run_scale_job: scale and crop are
    supplied by the caller (the GUI's manual "Set Scale"/"Set Crop Region"
    dialogs) instead of detected, since there's nothing to detect.

    scale_by_name: {file_name: mm_per_pixel} -- every readable file is
    expected to have an entry (the GUI always fully populates this first,
    whether by broadcasting one batch-wide value or via a completed
    per-image review); a file missing here is skipped and flagged rather
    than failing the whole batch, so this stays safe to call directly
    (e.g. from a test) with a partial dict too.
    scale_source_by_name: {file_name: SCALE_SOURCE_MANUAL |
    SCALE_SOURCE_MANUAL_BATCH} -- recorded in the CSV's scale_source
    column, same as the auto pipeline's measured/batch_median/page_median.
    crop_bbox_by_name: None means the whole batch skips cropping -- every
    image is saved at its original size. Otherwise {file_name: (x1, y1,
    x2, y2)}; each file must have its own entry (clamped again here,
    defensively, against that file's actual dimensions).

    Saves <stem>_cropped.<ext> into <output_folder>/scale/ -- the exact
    same subdirectory and filename convention run_scale_job uses, so
    segmetric.mask/segment/landmark's matching code (which strips exactly
    this "_cropped" suffix) picks it up with no changes on their end.
    """
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
