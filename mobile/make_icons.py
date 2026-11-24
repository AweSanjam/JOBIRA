#!/usr/bin/env python3
"""Draw the app icons for the mobile dashboard (needs Pillow; run once).

    python3 mobile/make_icons.py "J" "#4355B9" "#DEE0FF"        # JOBIRA
    python3 mobile/make_icons.py "J2" "#006A60" "#9EF2E4"       # JOBIRA 2

Writes icon-192.png, icon-512.png and icon-maskable-512.png next to this file.
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

FONT = "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"
HERE = os.path.dirname(os.path.abspath(__file__))


def draw(size, text, bg, fg, maskable):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if maskable:  # full bleed; launcher applies its own mask, keep glyph in the safe zone
        d.rectangle([0, 0, size, size], fill=bg)
        scale = 0.34
    else:
        d.rounded_rectangle([0, 0, size - 1, size - 1], radius=int(size * 0.28), fill=bg)
        scale = 0.46
    font = ImageFont.truetype(FONT, int(size * scale * (0.8 if len(text) > 1 else 1)))
    box = d.textbbox((0, 0), text, font=font)
    w, h = box[2] - box[0], box[3] - box[1]
    d.text(((size - w) / 2 - box[0], (size - h) / 2 - box[1]), text, font=font, fill=fg)
    return img


def main():
    text, bg, fg = sys.argv[1], sys.argv[2], sys.argv[3]
    draw(192, text, bg, fg, False).save(os.path.join(HERE, "icon-192.png"))
    draw(512, text, bg, fg, False).save(os.path.join(HERE, "icon-512.png"))
    draw(512, text, bg, fg, True).save(os.path.join(HERE, "icon-maskable-512.png"))


if __name__ == "__main__":
    main()
