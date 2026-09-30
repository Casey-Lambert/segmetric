
import os
from dataclasses import dataclass, field

from segmetric.scale.core.model import ScaleSettings
from segmetric.scale.core.pipeline import run_scale_job
from segmetric.set.core.model import Preset
from segmetric.tag.core.naming import DEFAULT_OUTPUT_FORMAT, OcrRegion
from segmetric.tag.core.pipeline import run_panel_split_job

from .summary import summary_path_for, write_summary_csv


@dataclass
class PrepareJobResult:
    output_dir: str
    panels_saved: int = 0
    panels_cropped: int = 0
    summary_csv_path: str = ""
    scale_rows: list = field(default_factory=list)  # (file_name, mm_per_pixel, scale_source)
    tag_files_skipped: list = field(default_factory=list)
    scale_files_skipped: list = field(default_factory=list)
    interrupted: bool = False
    interrupted_during: str = ""  # "tag" or "scale", only used if interrupted



def run_prepare_job(
    input_folder,
    output_folder,
    rows,
    cols,
    use_cv_naming,
    ocr_region: OcrRegion,
    gpu,
    output_format,
    scale_settings: ScaleSettings,
    preset: Preset = None,
    progress_cb=None,
    should_stop=None,
    crop_output_format=DEFAULT_OUTPUT_FORMAT,
):
    """Run segmetric.tag split/name pipeline, then segmetric.scale's
    detect/crop pipeline on that output, then merge the two into one combined
    summary.csv
    """

    def report(fraction, message):
        if progress_cb is not None:
            progress_cb(fraction, message)

    result = PrepareJobResult(output_dir=output_folder)

    ##------------------------------------------------------------ step 1: tag
    report(0.0, "Stage 1/2 — splitting and naming panels…")
    tag_result = run_panel_split_job(
        input_folder,
        output_folder,
        rows,
        cols,
        use_cv_naming,
        progress_cb=lambda frac, msg: report(frac * 0.5, msg),
        gpu=gpu,
        ocr_region=ocr_region,
        should_stop=should_stop,
        output_format=output_format,
    )
    result.panels_saved = tag_result.panels_saved
    result.tag_files_skipped = tag_result.files_skipped

    if tag_result.interrupted:
        result.interrupted = True
        result.interrupted_during = "tag"
        report(
            0.5,
            f"Stopped during panel splitting — {tag_result.panels_saved} "
            "panel(s) saved. Scale step skipped.",
        )
        return result

    #--------------------------------------------------------- step 2: scale
    report(0.5, "Stage 2/2 — detecting markers, computing scale, cropping…")
    scale_result = run_scale_job(
        tag_result.output_dir,  # <output>/panels, feeding straight into scale
        output_folder,
        settings=scale_settings,
        progress_cb=lambda frac, msg: report(0.5 + frac * 0.5, msg),
        should_stop=should_stop,
        # Panels are numbered sequentially per source page (rows*cols per
        # page), so the batch-median fallback should be computed per page,
        # not across every page in the run -- see run_scale_job's own
        # docstring for group_size.
        group_size=rows * cols,
        output_format=crop_output_format,
    )
    result.panels_cropped = scale_result.panels_cropped
    result.scale_rows = scale_result.scale_rows
    result.scale_files_skipped = scale_result.files_skipped
    if scale_result.interrupted:
        result.interrupted = True
        result.interrupted_during = "scale"

    #------------------------------------------------------ join summary
    scale_csv_path = os.path.join(scale_result.output_dir, "scales.csv")
    if os.path.exists(scale_csv_path):
        summary_path = summary_path_for(output_folder)
        write_summary_csv(scale_csv_path, summary_path, preset=preset)
        result.summary_csv_path = summary_path

    if result.interrupted:
        report(
            1.0,
            f"Stopped — {result.panels_cropped} image(s) cropped. "
            f"Summary saved to {result.summary_csv_path or '(not written)'}.",
        )
    else:
        report(
            1.0,
            f"Done — {result.panels_saved} panel(s) saved, "
            f"{result.panels_cropped} cropped. Summary saved to {result.summary_csv_path}.",
        )

    return result




