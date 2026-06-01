"""Generate a simple app icon (assets/icon.ico) using Pillow."""

from pathlib import Path
from PIL import Image, ImageDraw

SIZES = [16, 32, 48, 64, 128, 256]
OUT = Path(__file__).resolve().parent.parent / "assets" / "icon.ico"


def draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = size // 8
    # Dark circle background
    draw.ellipse([pad, pad, size - pad, size - pad], fill=(30, 30, 30, 240))
    # Green ring
    ring = size // 6
    draw.ellipse(
        [pad + ring // 2, pad + ring // 2, size - pad - ring // 2, size - pad - ring // 2],
        outline=(76, 195, 247, 255),
        width=max(size // 12, 2),
    )
    # Center dot
    cx, cy = size // 2, size // 2
    r = size // 8
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(102, 187, 106, 255))
    return img


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    images = [draw_icon(s) for s in SIZES]
    images[0].save(OUT, format="ICO", sizes=[(s, s) for s in SIZES], append_images=images[1:])
    print(f"Icon saved to {OUT}")


if __name__ == "__main__":
    main()
