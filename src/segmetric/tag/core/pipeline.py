import logging
import os
import time
from dataclasses import dataclass, field

import cv2
from PIL import Image

from .discovery import find_input_files
from .errors import SegMetricError
from .naming import (
    DEFAULT_OUTPUT_FORMAT,
    OcrRegion,
    cv_filename,
    get_ocr_reader,
    ocr_label_for_panel,
    sequential_filename,
)
from .splitting import load_first_page, split_into_grid

PANELS_SUBDIR = "panels"


@dataclass
class JobResult:
    output_dir: str
    run_id: str
    files_processed: list = field(default_factory=list)
    files_skipped: list = field(default_factory=list)  # (filename, reason)
    panels_saved: int = 0
    interrupted: bool = False


def _make_panels_output_dir(output_folder):
    panels_dir = os.path.join(output_folder, PANELS_SUBDIR)
    try:
        os.makedirs(panels_dir, exist_ok=True)
    except OSError as exc:
        raise SegMetricError(
            f"Could not create the output folder '{panels_dir}': {exc.strerror}."
        ) from exc
    return panels_dir


def _make_logger(panels_dir):
    logger = logging.getLogger(f"segmetric.tag.pipeline.{id(panels_dir)}")
    logger.setLevel(logging.ERROR)
    logger.propagate = False
    handler = logging.FileHandler(os.path.join(panels_dir, "segmetric_tag.log"))
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.handlers = [handler]
    return logger


def _save_panel(panel_bgr, out_path):
    Image.fromarray(cv2.cvtColor(panel_bgr, cv2.COLOR_BGR2RGB)).save(
        out_path, dpi=(1200, 1200)
    )


def run_panel_split_job(
    input_folder,
    output_folder,
    rows,
    cols,
    use_cv_naming,
    progress_cb=None,
    gpu=True,
    ocr_region: OcrRegion = OcrRegion(),
    should_stop=None,
    output_format=DEFAULT_OUTPUT_FORMAT,
):
    """Split every PDF/PNG/JPG/TIFF in input_folder into a rows x cols grid of
    panels and save them to <output_folder>/panels/ as output_format files
    (tiff/png/jpeg).

    progress_cb, if given, is called as progress_cb(fraction_0_to_1, message).
    Per-file failures are logged and skipped rather than aborting the whole job;
    invalid parameters (bad rows/cols, missing folders) raise SegMetricError
    immediately. Full tracebacks for skipped files go to segmetric_tag.log inside
    the output folder.

    should_stop, if given, is a zero-arg callable checked between files and
    between panels; when it returns True the job stops early (after finishing
    whatever panel is currently being saved) and JobResult.interrupted is set.
    """
    if rows < 1 or cols < 1:
        raise SegMetricError("Rows and columns must both be at least 1.")

    input_files = find_input_files(input_folder)
    panels_dir = _make_panels_output_dir(output_folder)
    logger = _make_logger(panels_dir)

    reader = get_ocr_reader(gpu=gpu) if use_cv_naming else None

    run_id = time.strftime("%Y%m%d_%H%M%S")
    result = JobResult(output_dir=panels_dir, run_id=run_id)

    def stop_requested():
        return should_stop is not None and should_stop()

    panel_count = 0
    total_files = len(input_files)

    def report(fraction, message):
        if progress_cb is not None:
            progress_cb(fraction, message)

    report(0.0, f"Found {total_files} file(s) in {input_folder}.")

    for file_number, file_path in enumerate(input_files, start=1):
        if stop_requested():
            result.interrupted = True
            break

        fname = os.path.basename(file_path)
        report(
            (file_number - 1) / total_files,
            f"Processing {file_number} of {total_files}: {fname}",
        )
        try:
            image = load_first_page(file_path)
            panels = split_into_grid(image, rows, cols)

            for panel_info in panels:
                if stop_requested():
                    result.interrupted = True
                    break

                panel_count += 1
                if use_cv_naming:
                    label = ocr_label_for_panel(panel_info["panel"], reader, ocr_region)
                    out_name = cv_filename(panel_count, run_id, label, output_format)
                else:
                    out_name = sequential_filename(panel_count, run_id, output_format)
                _save_panel(panel_info["panel"], os.path.join(panels_dir, out_name))

            if result.interrupted:
                break

            result.files_processed.append(fname)
            report(
                file_number / total_files,
                f"Saved {len(panels)} panel(s) from {fname}.",
            )
        except SegMetricError as exc:
            logger.error("Skipped %s: %s", fname, exc)
            result.files_skipped.append((fname, str(exc)))
            report(file_number / total_files, f"Skipped {fname}: {exc}")
        except Exception as exc:  # unexpected failure for this one file
            logger.error("Skipped %s: unexpected error", fname, exc_info=True)
            result.files_skipped.append((fname, "An unexpected error occurred."))
            report(
                file_number / total_files,
                f"Skipped {fname}: an unexpected error occurred (see segmetric_tag.log).",
            )

    result.panels_saved = panel_count
    if result.interrupted:
        stopped_fraction = (file_number - 1) / total_files
        report(
            stopped_fraction,
            f"Stopped — {panel_count} panel(s) saved to {panels_dir} before stopping.",
        )
    else:
        report(1.0, f"Done — {panel_count} panel(s) saved to {panels_dir}.")
    return result
