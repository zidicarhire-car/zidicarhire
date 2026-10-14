"""
Moves each car's single photo (Car.image) into the new photo gallery as its cover photo, resized and
with a thumbnail. The original upload is removed once the new copies are saved. A photo that can't be
read is left in place and reported, so nothing is lost.
"""
import logging

from django.db import migrations

logger = logging.getLogger(__name__)


def move_images(apps, schema_editor):
    from fleet.images import ImageProblem, save_photo

    Car = apps.get_model('fleet', 'Car')
    CarPhoto = apps.get_model('fleet', 'CarPhoto')
    for car in Car.objects.exclude(image=''):
        storage = car.image.storage
        name = car.image.name
        if not storage.exists(name):
            logger.warning('Photo %s for car %s is missing on disk; skipped', name, car.pk)
            continue
        try:
            with storage.open(name, 'rb') as upload:
                save_photo(car, upload, photo_model=CarPhoto, is_cover=True)
        except (ImageProblem, OSError) as exc:
            logger.warning('Could not move photo %s for car %s: %s', name, car.pk, exc)
            continue
        storage.delete(name)


class Migration(migrations.Migration):

    dependencies = [
        ('fleet', '0006_car_details_and_photos'),
    ]

    operations = [
        migrations.RunPython(move_images, migrations.RunPython.noop),
    ]
