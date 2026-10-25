"""Decode and re-encode uploaded raster images; filenames and EXIF are discarded."""
from io import BytesIO
from uuid import uuid4
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile


def prepare_image(upload):
    if upload.size > 8 * 1024 * 1024:
        raise ValidationError('Please choose a picture smaller than 8 MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            upload.seek(0)
            with Image.open(upload) as image:
                if image.format not in {'JPEG', 'PNG', 'WEBP'} or image.width * image.height > 20_000_000:
                    raise ValidationError('Use JPEG, PNG or WebP up to 20 megapixels.')
                image = ImageOps.exif_transpose(image).convert('RGB')
                image.thumbnail((2000, 2000))
                output = BytesIO()
                image.save(output, format='WEBP', quality=85)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombWarning, Image.DecompressionBombError) as exc:
        raise ValidationError('This picture could not be read safely. Choose another JPEG, PNG or WebP.') from exc
    return ContentFile(output.getvalue(), name=f'{uuid4().hex}.webp')
