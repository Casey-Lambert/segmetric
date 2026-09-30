

from PyQt6.QtCore import QThread, pyqtSignal

from segmetric.errors import SegMetricError

from ..core.pipeline import run_mask_job


class MaskJobWorker(QThread):
    """Runs the batch mask-generation + measurement job off the GUI thread."""

    progress = pyqtSignal(float, str)
    error = pyqtSignal(str)
    finished_ok = pyqtSignal(object)  # Mask result

    def __init__(self, matched_crops, filter_resolver, output_folder, metadata_preset=None):
        super().__init__()
        self.matched_crops = matched_crops
        self.filter_resolver = filter_resolver
        self.output_folder = output_folder
        self.metadata_preset = metadata_preset

    def run(self):
        try:
            result = run_mask_job(
                self.matched_crops,
                self.filter_resolver,
                self.output_folder,
                metadata_preset=self.metadata_preset,
                progress_cb=lambda frac, msg: self.progress.emit(frac, msg),
                should_stop=self.isInterruptionRequested,
            )
            self.finished_ok.emit(result)
        except SegMetricError as exc:
            self.error.emit(str(exc))
        except Exception:
            self.error.emit("An unexpected error occurred while running the batch.")



