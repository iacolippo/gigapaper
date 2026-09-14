"""Turns gigapaper.png into the app icon (assets/gigapaper.icns).

Run once when the artwork changes; the generated .icns is committed, so a
normal build needs neither this script nor Pillow:

    python3 -m venv /tmp/icon && /tmp/icon/bin/pip install pillow
    /tmp/icon/bin/python tools/make_icon.py

The source art is a squircle photographed on a light background with a drop
shadow baked in. A Dock icon needs the opposite: the squircle alone, on
transparency, sized to Apple's grid. Colour-keying the background out is not
an option — the cream paper of the "g" (236,233,228) is nearly the same colour
as the backdrop (244,243,241) — so the shape is traced instead: the squircle
is the only blue thing in the frame, so scanning each row for its blue extent
recovers the outline exactly, corner curves and all.
"""

import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "gigapaper.png"
OUT = ROOT / "assets" / "gigapaper.icns"

CANVAS = 1024  # the icon grid Apple's sizes are derived from
BODY = 824  # the squircle itself, leaving a 100px margin for the shadow
SUPERSAMPLE = 4  # trace at 4x so the traced edge antialiases when scaled down

# The blue of the squircle against a light grey backdrop. Generous, since the
# top edge is a much lighter blue than the bottom.
def is_blue(r: int, g: int, b: int) -> bool:
    return b > 120 and b - r > 70


def trace(im: Image.Image) -> Image.Image:
    """Alpha mask of the squircle: per row, the span between its blue edges.

    Filling the whole span rather than the blue pixels keeps the white "g"
    inside the shape — it is opaque icon, not background.
    """
    w, h = im.size
    px = im.load()
    mask = Image.new("L", (w, h), 0)
    fill = mask.load()
    for y in range(h):
        left = right = None
        for x in range(w):
            if is_blue(*px[x, y]):
                if left is None:
                    left = x
                right = x
        if left is not None:
            for x in range(left, right + 1):
                fill[x, y] = 255
    return mask


def shadow(size: int) -> Image.Image:
    """The soft drop shadow macOS icons bake into their artwork."""
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    body = Image.new("RGBA", (BODY, BODY), (0, 0, 0, 70))
    margin = (size - BODY) // 2
    layer.paste(body, (margin, margin + int(size * 0.012)), body)
    return layer.filter(ImageFilter.GaussianBlur(size * 0.022))


def main() -> int:
    if not SOURCE.exists():
        print(f"no source art at {SOURCE}", file=sys.stderr)
        return 1

    art = Image.open(SOURCE).convert("RGB")
    mask = trace(art)
    art.putalpha(mask)

    # Crop to the shape and drop the (now transparent) backdrop entirely.
    art = art.crop(mask.getbbox())

    # Square it off: the traced box is a few pixels taller than wide from the
    # gradient at the top edge, which would otherwise stretch the squircle.
    side = max(art.size)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    square.paste(art, ((side - art.width) // 2, (side - art.height) // 2), art)

    big = CANVAS * SUPERSAMPLE
    canvas = shadow(big)
    body = square.resize((BODY * SUPERSAMPLE,) * 2, Image.LANCZOS)
    offset = (big - body.width) // 2
    canvas.alpha_composite(body, (offset, offset))
    master = canvas.resize((CANVAS, CANVAS), Image.LANCZOS)

    iconset = OUT.parent / "gigapaper.iconset"
    iconset.mkdir(parents=True, exist_ok=True)
    for size in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            px = size * scale
            name = f"icon_{size}x{size}{'@2x' if scale == 2 else ''}.png"
            master.resize((px, px), Image.LANCZOS).save(iconset / name)

    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(OUT)], check=True)
    for f in iconset.iterdir():
        f.unlink()
    iconset.rmdir()
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
