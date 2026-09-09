"""Raster image input boundary (placeholder, reserved in T0001).

Future responsibility (not implemented yet): reading JPG/PNG inputs and
routing them through one unified normalizer instead of per-format model
adapters, as required by the product boundary rules. Expected duties in
later tickets:

- JPEG EXIF rotation handling;
- PNG alpha channel handling;
- grayscale and palette images;
- ICC color profiles;
- DPI metadata;
- RGB conversion;
- source image hashing;
- unified page coordinates.

Nothing in this package may decode images, call models or access the
network in T0001.
"""

from __future__ import annotations
