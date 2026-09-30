---
layout: page
title: segmetric.mask
permalink: /mask.html
---

# segmetric.mask

Uses the cropped images and the scale.csv from `segmetric.tag` +
`segmetric.scale` or `segmetric.prepare` and generates a binary mask. It
then measures its axis-corrected length and width based on the widest
and longest part of the mask. It then lets you manually correct the mask
with a brush tool, as well as tag the files as "blank", "damaged" or
with a unique tag provided by the user.

SegMetric currently comes with three pre-tuned masking filters adjusted
to honeybee (*Apis mellifera*) forewing, hindwings, and legs. Custom
filters can be created, named and saved; either by adjusting the
pre-tuned filters or starting from blank filters. Created filters are
saved as .JSON files.

Single-object batches use one filter for the whole batch run. If you
load in an *Object ID* you can run mixed-object batches. This is done by
assigning filters based on the preset *Object ID* metadata file
generated in `segmetric.set`. Identified *Object ID*s for the batch are
listed at the top of the filter assignment tool. Multiple *Object ID*s
can be assigned to a filter by listing them using a ", ". The *Object
ID* - filter assignment is savable as a template which can be uploaded
in future batches.

Output is saved as `<output>/masks/*.png` and the measurements and any
metadata are saved as `<output>/masks/mask_measurements.csv`.

## Run it

```bash
segmetric-mask
```

[← Back to all tools](index.html)
