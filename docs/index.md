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
      <th style="border: 1px solid #ccc; padding: 8px;"></th>
      <th style="border: 1px solid #ccc; padding: 8px; text-align: left;">Tool</th>
      <th style="border: 1px solid #ccc; padding: 8px; text-align: left;">What it does</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td rowspan="4" style="border: 1px solid #ccc; padding: 8px; background-color: #96b4d2; text-align: center; font-weight: bold; vertical-align: middle;">prepare</td>
      <td style="border: 1px solid #ccc; padding: 8px; background-color: #eaf1f8;"><a href="tag.html"><code>segmetric.tag</code></a></td>
      <td style="border: 1px solid #ccc; padding: 8px; background-color: #eaf1f8;">Splits scans into named panels, optionally using OCR</td>
    </tr>
    <tr>
      <td style="border: 1px solid #ccc; padding: 8px; background-color: #eaf1f8;"><a href="set.html"><code>segmetric.set</code></a></td>
      <td style="border: 1px solid #ccc; padding: 8px; background-color: #eaf1f8;">Builds filename-to-metadata presets, including an Object ID</td>
    </tr>
    <tr>
      <td style="border: 1px solid #ccc; padding: 8px; background-color: #eaf1f8;"><a href="scale.html"><code>segmetric.scale</code></a></td>
      <td style="border: 1px solid #ccc; padding: 8px; background-color: #eaf1f8;">Computes real-world scale from ArUco markers (or manual calibration) and crops</td>
    </tr>
    <tr>
      <td style="border: 1px solid #ccc; padding: 8px; background-color: #eaf1f8; border-top: 2px solid #96b4d2;"><a href="prepare.html"><code>segmetric.prepare</code></a></td>
      <td style="border: 1px solid #ccc; padding: 8px; background-color: #eaf1f8; border-top: 2px solid #96b4d2;"><em>Combines tag + set + scale into one streamlined run</em></td>
    </tr>
    <tr>
      <td rowspan="4" style="border: 1px solid #ccc; padding: 8px; background-color: #8cbe8c; text-align: center; font-weight: bold; vertical-align: middle;">measure</td>
      <td style="border: 1px solid #ccc; padding: 8px; background-color: #eef6ee;"><a href="mask.html"><code>segmetric.mask</code></a></td>
      <td style="border: 1px solid #ccc; padding: 8px; background-color: #eef6ee;">Generates and corrects a binary mask per object, measures length/width</td>
    </tr>
    <tr>
      <td style="border: 1px solid #ccc; padding: 8px; background-color: #eef6ee;"><a href="segment.html"><code>segmetric.segment</code></a></td>
      <td style="border: 1px solid #ccc; padding: 8px; background-color: #eef6ee;">Click-select follow-up to mask: detects and measures cells/segments</td>
    </tr>
    <tr>
      <td style="border: 1px solid #ccc; padding: 8px; background-color: #eef6ee;"><a href="landmark.html"><code>segmetric.landmark</code></a></td>
      <td style="border: 1px solid #ccc; padding: 8px; background-color: #eef6ee;">Freeform geometric-morphometric landmark placement</td>
    </tr>
    <tr>
      <td style="border: 1px solid #ccc; padding: 8px; background-color: #eef6ee; border-top: 2px solid #8cbe8c;"><a href="measure.html"><code>segmetric.measure</code></a></td>
      <td style="border: 1px solid #ccc; padding: 8px; background-color: #eef6ee; border-top: 2px solid #8cbe8c;"><em>Runs mask + segment + landmark together in one shared shell</em></td>
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
