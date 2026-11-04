"""Validation for uploaded images (Phase 11 step 4).

`ImageField` already refuses anything Pillow cannot open, which rules out the obvious
"rename a script to .png" attack. What it does **not** do is bound the cost: there was
no size limit and no pixel limit anywhere, so a turf photo could be a 500 MB file, or a
20,000 x 20,000 PNG that unpacks to over a gigabyte in memory the moment anything tries
to read it — a decompression bomb, and the only thing standing between it and the worker
process was goodwill.

The limits are generous on purpose. A photo of a turf taken on a phone is two or three
megabytes; anything much past that is not a better photo.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

#: 5 MB. A phone camera's JPEG is well under this; a scan or a screenshot of a scan is not.
MAX_IMAGE_BYTES = 5 * 1024 * 1024

#: 6000 x 6000 is larger than any screen this will be shown on, and 36 megapixels is
#: already an uncomfortable amount of memory to decode.
MAX_IMAGE_PIXELS = 6000


def validate_image_upload(file) -> None:
    """Refuse images that are too large to be worth accepting.

    Raises `ValidationError` with a message a person can act on — "too big" is useless
    to somebody holding a photo that looks fine to them.
    """
    size = getattr(file, "size", None)
    if size is not None and size > MAX_IMAGE_BYTES:
        raise ValidationError(
            _("That image is %(mb).1f MB. The limit is %(limit)s MB — try a smaller one."),
            params={"mb": size / 1024 / 1024, "limit": MAX_IMAGE_BYTES // 1024 // 1024},
            code="image_too_large",
        )

    width = getattr(getattr(file, "image", None), "width", None)
    height = getattr(getattr(file, "image", None), "height", None)
    if width and height and (width > MAX_IMAGE_PIXELS or height > MAX_IMAGE_PIXELS):
        raise ValidationError(
            _("That image is %(w)sx%(h)s pixels. The limit is %(limit)s on each side."),
            params={"w": width, "h": height, "limit": MAX_IMAGE_PIXELS},
            code="image_too_large",
        )
