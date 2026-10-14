"""
Draws the PNG brand images with Pillow from the plate geometry in fleet/brand.py:

  static/img/apple-touch-icon.png  180 x 180 (iPhone home screen)
  static/img/og-image.png          1200 x 630 (link previews on WhatsApp, Facebook, X)

The PNGs are committed, so this only needs running again if the logo changes.
"""
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from PIL import Image, ImageDraw, ImageFont

from fleet import brand

SCALE = 4  # draw 4x larger, then shrink, for smooth edges


def _rounded(draw, box, s, ox, oy, fill=None, outline=None):
    x0, y0 = ox + box['x'] * s, oy + box['y'] * s
    x1, y1 = x0 + box['w'] * s, y0 + box['h'] * s
    width = max(1, round(box['stroke'] * s))
    # SVG strokes are centred on the edge; Pillow draws them inside, so grow the box by half a stroke.
    half = width / 2
    draw.rounded_rectangle((x0 - half, y0 - half, x1 + half, y1 + half), radius=(box['r'] * s) + half,
                           fill=fill, outline=outline, width=width)


def draw_plate(draw, s, ox, oy):
    """The mark at scale s with its SVG origin at (ox, oy)."""
    _rounded(draw, brand.PLATE, s, ox, oy, fill=brand.PLATE_YELLOW, outline=brand.BLACK)
    _rounded(draw, brand.PLATE_INNER, s, ox, oy, outline=brand.BLACK)
    for points, is_hole in brand.letter_polygons():
        draw.polygon([(ox + x * s, oy + y * s) for x, y in points],
                     fill=brand.PLATE_YELLOW if is_hole else brand.BLACK)


def _font(size):
    for name in ('Archivo-ExtraBold.ttf', 'arialbd.ttf', 'Arial Bold.ttf', 'DejaVuSans-Bold.ttf'):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def apple_touch_icon():
    size = 180 * SCALE
    fav = brand.FAVICON
    img = Image.new('RGB', (size, size), brand.PLATE_YELLOW)  # iOS rounds the corners itself
    draw = ImageDraw.Draw(img)
    s = size / 64
    inner = fav['inner']
    _rounded(draw, {**inner, 'stroke': inner['stroke'] * 1.3}, s, 0, 0, outline=brand.BLACK)
    draw.polygon([(x * s, y * s) for x, y in fav['z']], fill=brand.BLACK)
    return img.resize((180, 180), Image.LANCZOS)


def og_image(site_name):
    w, h = 1200 * SCALE, 630 * SCALE
    img = Image.new('RGB', (w, h), brand.INDIGO)
    draw = ImageDraw.Draw(img)

    s = 2.4 * SCALE                       # plate is 212 x 88 units, so about 509 x 211 px
    plate_w, plate_h = 224 * s, 120 * s
    ox = (w - plate_w) / 2
    oy = 70 * SCALE
    draw_plate(draw, s, ox, oy)

    title = _font(96 * SCALE)
    tagline = _font(44 * SCALE)
    y = oy + plate_h + 10 * SCALE
    for text, font, colour, gap in ((site_name, title, '#FFFFFF', 34),
                                    ('Car hire across Kenya. Pay with M-Pesa.', tagline, '#C9CEE4', 0)):
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        draw.text(((w - (right - left)) / 2 - left, y - top), text, font=font, fill=colour)
        y += (bottom - top) + gap * SCALE
    draw.rectangle((0, h - 18 * SCALE, w, h), fill=brand.PLATE_YELLOW)
    return img.resize((1200, 630), Image.LANCZOS)


class Command(BaseCommand):
    help = 'Draws static/img/apple-touch-icon.png and static/img/og-image.png from the plate logo.'

    def handle(self, *args, **options):
        out = Path(settings.BASE_DIR) / 'static' / 'img'
        apple_touch_icon().save(out / 'apple-touch-icon.png', optimize=True)
        og_image(settings.BUSINESS['name']).save(out / 'og-image.png', optimize=True)
        self.stdout.write(self.style.SUCCESS(f'Wrote apple-touch-icon.png and og-image.png to {out}'))
