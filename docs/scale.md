---
layout: page
title: segmetric.scale
permalink: /scale.html
---

# segmetric.scale

Crops images, and sets image scale to be used in downstream processes.
User may use ArUco markers to automatically crop and scale each image, or
use manual two point calibration. Output crops saved as
`<output>/scales/` and scale file is saved as `<output>/scales/scales.csv`
as mm/pixel.

## ArUco

Scale generation is based on 4 markers placed in a square array placed
around the image. Markers are then cropped out of image so they do not
interfere with downstream filtering and detection processes.

- Crop region is adjustable within the array. Markers are provided in the
  *Template* files or can be generated at
  [chev.me/arucogen](https://chev.me/arucogen/).
- If ArUco detection fails to detect 4 markers, SegMetric optionally
  falls back to plain shape detection (blob detection), looking for
  square markers in the image.
  - Within the GUI, users can adjust detection threshold for ArUco
    markers and the size thresholds for blob detection. These settings
    can be saved and referenced later.
- If scale generation fails, SegMetric uses the file sequence, and
  averages together the scales from the original set the image belonged
  to. Whether the scale is a direct measurement, or a batch median, is
  saved in the output `scales.csv` as mm/pixel.
  - Example: 4 scans, each split into 16 panels, creates panel sets 1-16,
    17-32, 33-48, and 49-64. If scaling fails on the 15th image in the
    batch, it will take the average scale for the 1st through 16th panel
    in the sequence and assign that to the 15th image. If the 39th image
    fails, then it would assign the average scale for the 33rd-48th
    images in the batch.

## Manual scaling

Prompted by clicking *No markers present*. In this window scale is set
based on two point calibration. Scale can be set manually for each
image, or applied across the process batch. Batch application means you
only need to have one scale object in an original scan, and apply across
all panels generated from that original. Crop region (if desired) is set
per image or across the batch with a click and drag function.

Currently, manual scaling is only available in `segmetric.scale` and is
not available through `segmetric.prepare`. If there are no markers
present, run `tag`, `scale`, then `mask`/`segment`/`landmark` as separate
steps.

## Run it

```bash
segmetric-scale
```

[← Back to all tools](index.html)
