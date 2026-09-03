from PyQt6.QtCore import QThread, pyqtSignal

from ..core.detection import segment_cells


class DetectWorker(QThread):
    """Runs segment_cells for ONE crop off the GUI thread -- the Sato +
    watershed computation takes a few seconds, and every crop needs it
    before any click-selection is even possible, so this keeps the review
    window responsive while it runs.
    """

    finished_ok = pyqtSignal(object, int, object)  # labeled, n_cells, vein_mask
    error = pyqtSignal(str)

    def __init__(self, image_rgb, wing_mask, detection_settings):
        super().__init__()
        self.image_rgb = image_rgb
        self.wing_mask = wing_mask
        self.detection_settings = detection_settings

    def run(self):
        try:
            labeled, n_cells, vein_mask = segment_cells(
                self.image_rgb, self.wing_mask, self.detection_settings
            )
            self.finished_ok.emit(labeled, n_cells, vein_mask)
        except Exception as exc:  # noqa: BLE001 -- surfaced to the GUI, not swallowed
            self.error.emit(f"Cell detection failed: {exc}")
