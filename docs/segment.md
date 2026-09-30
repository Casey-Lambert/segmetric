---
layout: page
title: segmetric.segment
permalink: /segment.html
---

# segmetric.segment

Follow up process to `segmetric.mask`. `segmetric.segment` detects
candidate cell regions using a ridge filter. It is highly suggested that
users run `segmetric.mask` first, and load them into the program before
running. When paired with a mask, the ridge filter is constrained to the
mask area, increasing accuracy and efficiency. Masks that were tagged
"blank" in `segmetric.mask` are excluded by default, but this feature
can be toggled off. Without a mask, `segmetric.segment` applies the
ridge filter to the entire image area.

After applying the filter, the program prompts you to click-to-select
the target regions for measurement. The tagging function (e.g. tagging
an item as "damaged") is the same as in `segmetric.mask`.

Output saved to `<output>/segment_masks/*.png` and measurements are
saved within `segment_measurements.csv`.

## Ridge filters

SegMetric comes with three pre-tuned ridge filters adjusted to honeybee
(*Apis mellifera*) forewings, hindwings, and legs. Detection thresholds
and the step sequence are both programmable. Users may choose to adjust
these filters, or start from scratch. Filters can be renamed, and are
savable/loadable .JSON files. In mixed object batches, users will load
in a metadata .JSON file generated with `segmetric.set` and use *Object
ID* to assign filters. Users can measure multiple objects in the image
at a time by creating a "sequence" which is saved alongside filter data.

## Cell selection

`segmetric.segment` will walk you through a select & correct process.
Multiple cells can be clicked to merge them together into a single
measurement. Once selected, you may open up the correction tool —
identical to the brush correction tool in `segmetric.mask`. If sequence
measurement was set, the user can toggle back and forth between the
assigned measurements. Clicking to process saves the measurements.

## Run it

```bash
segmetric-segment
```

[← Back to all tools](index.html)
