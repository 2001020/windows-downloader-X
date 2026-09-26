"""Generate the application icons (PNG, ICO, ICNS) with Pillow.

    python tools/make_icons.py
"""

import os

from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIZE = 1024


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(len(a)))


def draw_icon():
    s = SIZE
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))

    # Rounded-square background with a vertical blue gradient.
    grad = Image.new("RGBA", (s, s))
    gd = ImageDraw.Draw(grad)
    top, bottom = (38, 132, 255), (0, 72, 186)
    for y in range(s):
        gd.line([(0, y), (s, y)], fill=lerp(top, bottom, y / (s - 1)) + (255,))
    mask = Image.new("L", (s, s), 0)
    margin = int(s * 0.07)
    ImageDraw.Draw(mask).rounded_rectangle([margin, margin, s - margin, s - margin], radius=int(s * 0.2), fill=255)
    shadow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle([margin, margin + s * 0.015, s - margin, s - margin + s * 0.015],
                                             radius=int(s * 0.2), fill=(0, 0, 0, 90))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(s * 0.015)))
    img.paste(grad, (0, 0), mask)

    d = ImageDraw.Draw(img)
    # Optical disc.
    cx, cy, r = s * 0.5, s * 0.44, s * 0.27
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(245, 248, 255, 255))
    ring = r * 0.78
    d.ellipse([cx - ring, cy - ring, cx + ring, cy + ring], outline=(205, 220, 245, 255), width=int(s * 0.012))
    hole = r * 0.3
    d.ellipse([cx - hole, cy - hole, cx + hole, cy + hole], fill=(200, 215, 240, 255))
    inner = r * 0.14
    d.ellipse([cx - inner, cy - inner, cx + inner, cy + inner], fill=lerp(top, bottom, 0.44) + (255,))

    # Download badge: circle with an arrow into a tray.
    bx, by, br = s * 0.7, s * 0.7, s * 0.17
    d.ellipse([bx - br - s * 0.018, by - br - s * 0.018, bx + br + s * 0.018, by + br + s * 0.018],
              fill=(0, 72, 186, 255))
    d.ellipse([bx - br, by - br, bx + br, by + br], fill=(22, 196, 127, 255))
    w = s * 0.03
    d.line([(bx, by - br * 0.55), (bx, by + br * 0.25)], fill="white", width=int(w * 1.1))
    d.polygon([(bx - br * 0.42, by - br * 0.02), (bx + br * 0.42, by - br * 0.02), (bx, by + br * 0.45)],
              fill="white")
    d.line([(bx - br * 0.5, by + br * 0.58), (bx + br * 0.5, by + br * 0.58)], fill="white", width=int(w * 0.8))
    return img


def main():
    icon = draw_icon()
    assets = os.path.join(ROOT, "common", "winiso", "assets")
    os.makedirs(assets, exist_ok=True)
    icon.resize((256, 256), Image.LANCZOS).save(os.path.join(assets, "icon.png"))
    icon.resize((48, 48), Image.LANCZOS).save(os.path.join(assets, "icon-48.png"))
    icon.resize((96, 96), Image.LANCZOS).save(os.path.join(assets, "icon-96.png"))
    icon.resize((256, 256), Image.LANCZOS).save(os.path.join(ROOT, "linux", "winiso-downloader.png"))
    icon.save(os.path.join(ROOT, "windows", "icon.ico"),
              sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    icon.save(os.path.join(ROOT, "macos", "icon.icns"))
    print("icons written")


if __name__ == "__main__":
    main()
