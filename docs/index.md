---
layout: default
title: SegMetric
permalink: /
---

<div style="text-align: center;">
  <img src="assets/images/logo.png" alt="SegMetric" width="600" style="display: block; margin: 0 auto;">
</div>

SegMetric is eight PyQt6 desktop tools that cover a full workflow: split a
scan into panels, build a naming/metadata scheme, compute a real-world
scale from ArUco markers (or set it manually), then mask, segment, and
landmark each object for measurement.

## The tools

<table style="width: 100%; border-collapse: collapse;">
  <thead>
    <tr>
      <th colspan="2" style="border: 1px solid #ccc; padding: 8px; text-align: left;">Tool</th>
      <th style="border: 1px solid #ccc; padding: 8px; text-align: left;">What it does</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td rowspan="3" style="border: 1px solid #ccc; padding: 8px; background-color: #96b4d2; text-align: center; font-weight: bold; vertical-align: middle;">prepare</td>
      <td style="border: 1px solid #ccc; padding: 8px; background-color: #eaf1f8;"><a href="tag.html"><code>tag</code></a></td>
      <td style="border: 1px solid #ccc; padding: 8px; background-color: #eaf1f8;">Splits scans into named panels, optionally using OCR</td>
    </tr>
    <tr>
      <td style="border: 1px solid #ccc; padding: 8px; background-color: #eaf1f8;"><a href="set.html"><code>set</code></a></td>
      <td style="border: 1px solid #ccc; padding: 8px; background-color: #eaf1f8;">Builds filename-to-metadata presets, including an Object ID</td>
    </tr>
    <tr>
      <td style="border: 1px solid #ccc; padding: 8px; background-color: #eaf1f8;"><a href="scale.html"><code>scale</code></a></td>
      <td style="border: 1px solid #ccc; padding: 8px; background-color: #eaf1f8;">Computes real-world scale from ArUco markers (or manual calibration) and crops</td>
    </tr>
    <tr>
      <td rowspan="3" style="border: 1px solid #ccc; padding: 8px; background-color: #8cbe8c; text-align: center; font-weight: bold; vertical-align: middle;">measure</td>
      <td style="border: 1px solid #ccc; padding: 8px; background-color: #eef6ee;"><a href="mask.html"><code>mask</code></a></td>
      <td style="border: 1px solid #ccc; padding: 8px; background-color: #eef6ee;">Generates and corrects a binary mask per object, measures length/width</td>
    </tr>
    <tr>
      <td style="border: 1px solid #ccc; padding: 8px; background-color: #eef6ee;"><a href="segment.html"><code>segment</code></a></td>
      <td style="border: 1px solid #ccc; padding: 8px; background-color: #eef6ee;">Click-select follow-up to mask: detects and measures cells/segments</td>
    </tr>
    <tr>
      <td style="border: 1px solid #ccc; padding: 8px; background-color: #eef6ee;"><a href="landmark.html"><code>landmark</code></a></td>
      <td style="border: 1px solid #ccc; padding: 8px; background-color: #eef6ee;">Freeform geometric-morphometric landmark placement</td>
    </tr>
  </tbody>
</table>

## Install

```bash
pip install segmetric-toolkit
```

This installs the SegMetric suite. Requires Python 3.10+.

If you want to edit the code: See the
[source install instructions](https://github.com/{{ site.repository }}#install-from-source-conda-for-development-and-editing)
in the repository.

## Links

- [Source code on GitHub](https://github.com/{{ site.repository }})
- [Package on PyPI](https://pypi.org/project/segmetric-toolkit/)
