# SegMetric

Tools for managing measuring

-   **`segmetric.set`** — Builds metadata presets used across SegMetric. Use an example file, or manually enter naming format. Converts items separated by "\_" to named columns in the output CSV. It also lets you set an *Object ID* which can be used across the suite to apply object specific processes within a batch run. Output is saved as a .JSON file.

-   **`segmetric.tag`** — splits images (upload .PDF, .PNG, .JPEG, .TIFF) into separate panels. Optionally names the new panels with computer vision (OCR) based on text in the images.

-   **`segmetric.scale`** — Crops images, and sets image scale to be used in downstream processes. User may use ArUco markers to automatically crop and scale each image, or use manual two point calibration. Output crops saved as `<output>/scales/` and scale file is saved as `<output>/scales/scales.csv` as mm/pixel.

    -   **ArUco** scale generation is based on 4 markers placed in a square array placed around the image. Markers are then cropped out of image so they do not interfere with downstream filtering and detection processes.
        -   Crop region is adjustable within the array (see *Upcoming Features* at the end of is README). Markers are provided in the *Template* files or can be generated at <https://chev.me/arucogen/> .
        -   If ArUco detection fails to detect 4 markers, SegMetric optionally falls back to plain shape detection (blob detection), looking for square markers in the image.
            -   Within GUI, users can adjust detection threshold for ArCuo markers and the the size thresholds for blob detection. These settings can be saved and referenced later.
        -   If scale generation fails, SegMetric used the file sequence, and averages together the scales from the original set the image belonged to. Weather the scale is a direct measurement, or a batch median is saved in the output `scales.csv` as mm/pixel in generated *scale* folder in the output location.
            -   Example: 4 scans, each split into 16 panels, creates panel sets 1-16, 17 - 32, 33-48, and 49-64. If scaling fails on the 15th image in the batch, it will take the average scale for the 1st through 16th panel in the sequence and assign that to the 15th image. If the 39th image fails, then it would assign the average scale for the 33rd- 48th images in the batch.
    -   **Manua**l scaling is prompted by clicking *No markers present*. In this window scale is set based on two point calibration. Scale can be set manually for each image, or applied across process batch. Batch application means you only need to have one scale object in an original scan, and apply across all panels generated from that original. Crop region (if desired) is set per image or across the batch with a click and drag function. Currently, manual scaling is only available in **`segmetric.scale`** and not not available through `segmetric.prepare` . If there is no markers present, user must run `tag`, `scale`, then `mask`/`segment`/`landmark` as separate steps.\

-   **`segmetric.prepare`** — combines `tag`, `scale` into one streamlined process with one input folder and one output folder. It works by calling `tag`'s and `scale`'s pipelines back to back, and optionally applies a `set` to each panel's own filename to add metadata columns to a combined ``` <output>/``summary.csv ```. It does not change how `tag` and `scale` work, it is convenience process calling existing pipelines as a library. Manual scaling is not available in **`segmetric.prepare`** . If there is no markers present, user must run `tag` and `scale` separately. Output panels are saved as `<output>/panels`.Output crops saved in `<output>/scales` and scale information is saved as `<output>/scales/scales.csv` as mm/pixel.

-   **`segmetric.mask`** — Uses the cropped images and the scale.csv from `segmetric.tag`+`segmetric.scale` or `segmetric.prepare` and, generates a binary mask. It then measures its axis-corrected length and width based on widest and longest part of the mark. It then lets you manually correct the mask with a brush tool, as well as tag the files as "blank", "damaged" or with a unique tag provided by the user. SegMetric currently comes with three pre-tuned masking filters adjusted to honeybee (*Apis mellifera*) forewing, hindwings, and legs. Custom filters can be created, named and saved; either by adjusting the pre-tuned filters or starting from blank filters. Created filters are saved as .JSON files. Single-object batches use one filter for the whole batch run. If you load in an *Object ID* you can run mixed-object batches. This is done by assigning filters based on the preset *Object ID* metadata file generated in `segmetric.set`*.* Identified *Object ID*s for the batch are listed at the top of the filter assignment tool. Multiple *Object ID*s can be assigned to a filter by listing them using a ", ". The *Object ID* - filter assignment is savable as a template which can be uploaded in future batches. Output is saved as `<output>/masks/*.png` and the measurements and any metadata is saved as ``` <output>/masks``/mask_measurements.csv ```.

-   **`segmetric.segment`** — Follow up process to `segmetric.mask`. **`segmetric.segment`** detects candidate cell regions using a ridge filter. It is highly suggested that users run `segmetric.mask` first, and load them into the program before running. When paired with a mask, the ridge filter is constrained to the mask area, increasing accuracy and efficiency. Masks that were tagged "blank" in `segmetric.mask` are excluded by default, but this feature can be toggled off. Without a mask, `segmetric.segment` defaults applies the ridge filter to the entire image area. After applying the filter, the program prompts you to click-to-select the target regions for measurement. Tagging function (I.e. tagging a item as "damaged") is the same as in **`segmetric.mask`** . Output saved to `<output>/segment_masks/*.png` and measurements are saved within `segment_measurements.csv` .

    -   **Ridge filters**: SegMetric comes with three pre-tuned ridge filters adjusted to honeybee (*Apis mellifera*) forewings, hindwings, and legs. Detection thresholds and the step sequence are both programmable. Users may choose to adjust these filters, or start from scratch. Filters can be renamed, and are savable/loadable .JSON files. In mixed object batches, users will load in metadata .JSON file generated with `segmetric.set` and use *Object ID* to assign filters. Users can measure multiple objects in the image at a time by creating a "sequence" which is saved alongside filter data.

    -   **Cell selection:** **`segmetric.segment`** will walk you through a select & correct process. Multiple cells can be click to merge them together into a single measurement. Once selected, you may open up the correction tool - identical to the brush correction tool in **`segmetric.mask`**. If sequence measurement was set, user can toggle back and forth between the assignmed measurements. Clicking to process save the measurements.

-   **`segmetric.landmark`** — Load in image scale, and complete classic geometric landmarking. Preset to easily translate into morphometric analysis. Click anywhere on a crop to place a landmark and double-click on any landmark to rename it. Drag to adjust the landmark, scroll to zoom and drag the image pan. An optional intergration with `segmetric.mask` mask will load the dimmed out mask as a refrence but does not constrain where you click. Output saved to `landmark_measurements.csv` row per crop, with each landmark's pixel and mm coordinates, along with number of landmarks placed, and centroid size in mm, and any carried over "blank", "damaged" or custom flags.

-   **`segmetric.measure`** — A convience shell similar to **`segmetric.prepare`** , consolidating `mask`, `segment`, and `landmark`. Load in scale, crops, optional metadata preset, and then set an output folder. Then tab trough the measurement type, selecting the combination of tools you want to run. Load in or create the various .JSON presets. Runs will always progress in the order Mask → Segment → Landmark. If Mask is run, downstream processes automatically pick up and apply the results. All processes work identical to the `mask`, `segment`, and `landmark` standalone processes. Output: each enabled stage's usual files, plus one `measure_summary.csv` outer-joining `mask_measurements.csv` / `segment_measurements.csv` / `landmark_measurements.csv` exist, by file name.\

## Install (PyPI)

This installs every SegMetric tool. Requires Python 3.10+.

``` bash
pip install segmetric-toolkit
```

If you want to edit the code itself (or run the tests), use the source install below instead.

## Install from source (conda, for development and editing)

``` bash
conda env create -f environment.yml
conda activate segmetric
```

This installs SegMetric via the `pip:` section of `environment.yml`.

If you already have a `segmetric` environment created, re-run:

``` bash
conda activate segmetric
pip install -e .
```

## Run

``` bash
segmetric-tag       # panel splitter
segmetric-set       # metadata preset builder
segmetric-scale     # ArUco scale, manual scale & crop
segmetric-prepare   # combined tool (tag, set, scale) 
segmetric-mask      # Generate object mask, manually correct and measure
segmetric-segment   # Split object into segments, correct & measure specific segments 
segmetric-landmark  # geometric/morphometric landmarking & centroid calculation
segmetric-measure   # combined tool (mask, segment, landmark shell) 
```

Equivalent: `python -m segmetric.tag` /`python -m segmetric.set` / `python -m segmetric.scale` / `python -m segmetric.prepare` / `python -m segmetric.mask` / `python -m segmetric.segment` / `python -m segmetric.landmark` / `python -m segmetric.measure`)

## Project layout

-   Errors
    -   `src/segmetric/errors.py` — `SegMetricError`, shared across every SegMetric tool.
-   Processing logic only, no PyQt.
    -   `src/segmetric/tag/core/`
    -   `src/segmetric/set/core/`
    -   `src/segmetric/scale/core/`
    -   `src/segmetric/prepare/core/`
    -   `src/segmetric/mask/core/`
    -   `src/segmetric/segment/core/`
    -   `src/segmetric/landmark/core/`
    -   `src/segmetric/measure/core/`
-   Calls
    -   `prepare/core/pipeline.py` calls `tag`'s and `scale`'s `run_*_job` functions directly
    -   `mask/core/pipeline.py`, `segment/core/pipeline.py`, and `landmark/core/pipeline.py` call `prepare/core/metadata.py`'s `apply_preset_to_filename` for their own metadata/object-id handling
    -   `segment/core/matching.py` calls `mask/core/tagging.py`'s `find_tagged_mask` to locate a crop's mask
    -   `landmark/core/matching.py` calls `segment/core/matching.py`'s `match_crops`
    -   `measure/core/pipeline.py` calls `mask`'s and `segment`'s matching functions.
    -   `measure/core/summary.py` performs a multi-CSV outer join.
-   GUIs
    -   Each [PyQt6 desktop app]{.underline} imports their own `core`
        -   `src/segmetric/tag/gui/`
        -   `src/segmetric/set/gui/`
        -   `src/segmetric/scale/gui/`
        -   `src/segmetric/prepare/gui/`
        -   `src/segmetric/mask/gui/`
        -   `src/segmetric/segment/gui/`
        -   `src/segmetric/landmark/gui/`
        -   `src/segmetric/measure/gui/`
            -   `measure/gui/main_window.py` embeds `segment`'s and `landmark`'s own `ReviewWindow` widgets directly. It also reuses `mask`'s `MaskJobWorker`/`CorrectionDialog`/`ReviewDialog`

### Future SegMetric steps processes will be published as sub-packages under `segmetric/`*Upcoming Features*

-   Ability to scale and crop images based on markers within the image, without having to encompass the object.

## Install testing package (advanced)

``` bash
pip install -e ".[dev]"
pytest
```

Installed separately , but . Once installed, running the command `pytest` runs every function under `tests/` and prints a pass/fail summary. This can be used if the user makes modifications to the code base and wants to verify those changes are compatible with the code base. The testing suite was developed using Claude Code Sonnet 5.\
\
\
