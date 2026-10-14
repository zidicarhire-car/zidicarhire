"""The data migration that moves each car's old single photo into the new gallery."""
import shutil
import tempfile
from io import BytesIO
from pathlib import Path

from django.core.files.base import ContentFile
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase, override_settings
from PIL import Image

MEDIA = tempfile.mkdtemp(prefix='zch-migration-media-')
BEFORE = [('fleet', '0006_car_details_and_photos')]
AFTER = [('fleet', '0008_remove_car_image')]


@override_settings(MEDIA_ROOT=MEDIA)
class MoveCarImageMigrationTests(TransactionTestCase):
    def tearDown(self):
        MigrationExecutor(connection).migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())
        shutil.rmtree(MEDIA, ignore_errors=True)

    def test_existing_photo_becomes_the_cover(self):
        executor = MigrationExecutor(connection)
        executor.migrate(BEFORE)
        apps = executor.loader.project_state(BEFORE).apps
        Location = apps.get_model('fleet', 'Location')
        Car = apps.get_model('fleet', 'Car')
        nairobi = Location.objects.get(slug='nairobi')

        buf = BytesIO()
        Image.new('RGB', (2400, 1500), (10, 120, 200)).save(buf, 'JPEG')
        with_photo = Car(location=nairobi, name='Axio', price_per_day=4000)
        with_photo.image.save('old-axio.jpg', ContentFile(buf.getvalue()), save=False)
        with_photo.save()
        old_file = Path(MEDIA) / with_photo.image.name
        missing = Car.objects.create(location=nairobi, name='Vitz', price_per_day=3000, image='cars/gone.jpg')
        Car.objects.create(location=nairobi, name='Prado', price_per_day=9000)

        executor = MigrationExecutor(connection)
        executor.migrate(AFTER)
        apps = executor.loader.project_state(AFTER).apps
        CarPhoto = apps.get_model('fleet', 'CarPhoto')

        photo = CarPhoto.objects.get(car_id=with_photo.pk)
        self.assertTrue(photo.is_cover)
        self.assertEqual((photo.width, photo.height), (1600, 1000))
        self.assertTrue((Path(MEDIA) / photo.thumbnail.name).exists())
        self.assertFalse(old_file.exists())                         # original removed once copied
        self.assertFalse(CarPhoto.objects.filter(car_id=missing.pk).exists())  # missing file skipped, no crash
        self.assertEqual(CarPhoto.objects.count(), 1)
