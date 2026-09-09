"""Image normalization boundary (placeholder, reserved in T0001).

Future responsibility (not implemented yet): the single unified image
normalization module that every raster input (pure-image PDF pages, JPG,
PNG) passes through before page quality judgment and model routing.
Expected duties in later tickets:

- JPEG EXIF rotation;
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
