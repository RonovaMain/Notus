"""Regenerate assets/icon.png and assets/icon.ico (needs Pillow: pip install pillow)."""
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "assets"
S = 1024  # supersampled canvas


def gradient(size, c1, c2):
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * size - 2)
            px[x, y] = tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))
    return img


def draw_icon() -> Image.Image:
    bg = gradient(S, (24, 20, 64), (112, 76, 255)).convert("RGBA")
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, S - 1, S - 1), radius=230, fill=255)
    bg.putalpha(mask)

    # soft highlight in the upper-left corner
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((-300, -380, 700, 420), fill=(255, 255, 255, 38))
    bg = Image.alpha_composite(bg, ImageChops.multiply(glow, Image.merge("RGBA", (mask, mask, mask, mask))))

    # the "N": two bars and a diagonal, cyan -> white gradient
    stroke = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(stroke)
    w = 96
    pts = [(300, 740), (300, 290), (724, 740), (724, 290)]
    d.line(pts, fill=255, width=w, joint="curve")
    for x, y in (pts[0], pts[1], pts[2], pts[3]):
        d.ellipse((x - w // 2, y - w // 2, x + w // 2, y + w // 2), fill=255)
    fill = gradient(S, (86, 224, 255), (255, 255, 255)).convert("RGBA")
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    layer.paste(fill, (0, 0), stroke)
    bg = Image.alpha_composite(bg, layer)

    # sparkle (a four-point star) in the top-right corner
    sp = Image.new("L", (S, S), 0)
    sd = ImageDraw.Draw(sp)
    cx, cy, r, k = 800, 230, 120, 22
    sd.polygon([(cx, cy - r), (cx + k, cy - k), (cx + r, cy), (cx + k, cy + k),
                (cx, cy + r), (cx - k, cy + k), (cx - r, cy), (cx - k, cy - k)], fill=255)
    star = Image.new("RGBA", (S, S), (255, 214, 102, 255))
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    layer.paste(star, (0, 0), sp)
    return Image.alpha_composite(bg, layer)


def main() -> None:
    OUT.mkdir(exist_ok=True)
    big = draw_icon()
    big.resize((256, 256), Image.LANCZOS).save(OUT / "icon.png")
    sizes = [16, 24, 32, 48, 64, 128, 256]
    big.save(OUT / "icon.ico", sizes=[(s, s) for s in sizes])
    big.resize((512, 512), Image.LANCZOS).save(OUT / "icon-512.png")
    print("icons written to", OUT)


if __name__ == "__main__":
    main()
