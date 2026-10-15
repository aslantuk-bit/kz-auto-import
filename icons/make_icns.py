"""icons/source.png (квадрат из Glif) → icons/app.icns по сетке значков macOS."""
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).parent
CANVAS, BODY, RADIUS = 1024, 824, 185   # сетка Apple: тело 824 px, скругление ~22,5%


def squircle(src):
    art = Image.open(src).convert("RGBA").resize((BODY, BODY), Image.LANCZOS)
    mask = Image.new("L", (BODY * 4, BODY * 4), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, BODY * 4 - 1, BODY * 4 - 1), RADIUS * 4, fill=255)
    art.putalpha(mask.resize((BODY, BODY), Image.LANCZOS))
    out = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    off = (CANVAS - BODY) // 2
    out.alpha_composite(art, (off, off))
    return out


def main():
    icon = squircle(HERE / "source.png")
    icon.save(HERE / "app.png")
    iconset = HERE / "app.iconset"
    iconset.mkdir(exist_ok=True)
    for size in (16, 32, 128, 256, 512):
        icon.resize((size, size), Image.LANCZOS).save(iconset / f"icon_{size}x{size}.png")
        icon.resize((size * 2, size * 2), Image.LANCZOS).save(iconset / f"icon_{size}x{size}@2x.png")
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(HERE / "app.icns")], check=True)
    print(HERE / "app.icns")


if __name__ == "__main__":
    sys.exit(main())
