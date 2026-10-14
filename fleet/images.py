"""
Car photo processing with Pillow: checks the upload really is a JPEG, PNG or WebP image, turns phone
photos the right way up, removes all metadata (including GPS location), and saves a web copy at most
1600px wide plus a 600px thumbnail, both as JPEG.
"""
import uuid
from io import BytesIO

from django.conf import settings
from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_FORMATS = {'JPEG', 'PNG', 'WEBP'}
FULL_WIDTH = 1600
FULL_QUALITY = 82
THUMB_WIDTH = 600
THUMB_QUALITY = 78
MAX_PIXELS = 50_000_000  # refuse absurdly large images (decompression bombs)


class ImageProblem(Exception):
    """The upload can't be used; the message says why and what to do."""


def _to_rgb(img):
    if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
        img = img.convert('RGBA')
        background = Image.new('RGB', img.size, (255, 255, 255))
        background.paste(img, mask=img.getchannel('A'))
        return background
    return img.convert('RGB') if img.mode != 'RGB' else img


def _jpeg(img, width, quality):
    if img.width > width:
        img = img.resize((width, round(img.height * width / img.width)), Image.LANCZOS)
    out = BytesIO()
    # Saving without exif=... drops all metadata, including the phone's GPS location.
    img.save(out, 'JPEG', quality=quality, optimize=True, progressive=True)
    return out.getvalue(), img.size


def process_upload(upload):
    """
    Returns (full ContentFile, thumbnail ContentFile, width, height) for a car photo.
    Raises ImageProblem with a message the uploader can act on.
    """
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    size = getattr(upload, 'size', None)
    if size is not None and size > max_bytes:
        raise ImageProblem(f'{getattr(upload, "name", "That photo")} is over {settings.MAX_UPLOAD_MB} MB. '
                           'Choose a smaller photo or resize it.')
    data = upload.read()
    if len(data) > max_bytes:
        raise ImageProblem(f'That photo is over {settings.MAX_UPLOAD_MB} MB. Choose a smaller photo or resize it.')
    try:
        with Image.open(BytesIO(data)) as probe:
            fmt = probe.format
            if probe.width * probe.height > MAX_PIXELS:
                raise ImageProblem('That photo has too many pixels. Resize it to under 8000px wide and try again.')
            probe.verify()
        img = Image.open(BytesIO(data))
        img.load()
    except ImageProblem:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        raise ImageProblem("That file isn't a photo we can read. Upload a JPEG, PNG or WebP image.")
    if fmt not in ALLOWED_FORMATS:
        raise ImageProblem(f'{fmt or "That"} files are not accepted. Upload a JPEG, PNG or WebP image.')

    img = _to_rgb(ImageOps.exif_transpose(img))
    full, (width, height) = _jpeg(img, FULL_WIDTH, FULL_QUALITY)
    thumb, _ = _jpeg(img, THUMB_WIDTH, THUMB_QUALITY)
    name = uuid.uuid4().hex
    return ContentFile(full, name=f'{name}.jpg'), ContentFile(thumb, name=f'{name}-600.jpg'), width, height


def save_photo(car, upload, photo_model=None, is_cover=None):
    """Processes an upload and stores it as a new CarPhoto of `car`. Returns the photo."""
    from .models import CarPhoto

    model = photo_model or CarPhoto
    full, thumb, width, height = process_upload(upload)
    existing = model.objects.filter(car=car)
    photo = model(car=car, width=width, height=height,
                  order=(max((p.order for p in existing), default=-1) + 1),
                  is_cover=not existing.exists() if is_cover is None else is_cover)
    photo.image.save(full.name, full, save=False)
    photo.thumbnail.save(thumb.name, thumb, save=False)
    photo.save()
    return photo
