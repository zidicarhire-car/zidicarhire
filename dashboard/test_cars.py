"""Cars and photos: upload checks, resizing, ordering, deleting files, duplicating, the car page."""
import json
import shutil
import tempfile
from io import BytesIO
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from PIL import Image

from bookings.pricing import daily_rate_for, quote
from fleet.images import ImageProblem, process_upload
from fleet.models import Car, CarPhoto
from fleet.test_utils import make_car, make_location, make_point, trip

from .models import StaffProfile

User = get_user_model()
MEDIA = tempfile.mkdtemp(prefix='zch-test-media-')


def image_file(name='car.jpg', size=(800, 500), fmt='JPEG', color=(200, 30, 30), exif=None, mode='RGB'):
    buf = BytesIO()
    img = Image.new(mode, size, color)
    kwargs = {'exif': exif} if exif is not None else {}
    img.save(buf, fmt, **kwargs)
    return SimpleUploadedFile(name, buf.getvalue(), content_type=f'image/{fmt.lower()}')


def stored_size(field):
    with field.storage.open(field.name, 'rb') as fh:
        with Image.open(fh) as img:
            return img.size, img.getexif()


@override_settings(MEDIA_ROOT=MEDIA, MAX_UPLOAD_MB=2)
class ImageProcessingTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def test_large_photo_is_resized_with_thumbnail(self):
        full, thumb, width, height = process_upload(image_file(size=(3200, 2000)))
        self.assertEqual((width, height), (1600, 1000))
        with Image.open(BytesIO(full.read())) as img:
            self.assertEqual((img.format, img.size), ('JPEG', (1600, 1000)))
        with Image.open(BytesIO(thumb.read())) as img:
            self.assertEqual(img.size, (600, 375))

    def test_phone_rotation_is_fixed_and_location_removed(self):
        exif = Image.Exif()
        exif[0x0112] = 6                      # orientation: rotate 90 degrees
        exif[0x8825] = {2: (1.0, 17.0, 0.0)}  # GPS info
        full, _, width, height = process_upload(image_file(size=(400, 200), exif=exif.tobytes()))
        self.assertEqual((width, height), (200, 400))
        with Image.open(BytesIO(full.read())) as img:
            self.assertEqual(dict(img.getexif()), {})

    def test_png_and_webp_are_accepted(self):
        process_upload(image_file('a.png', fmt='PNG', mode='RGBA', color=(0, 0, 0, 0)))
        process_upload(image_file('a.webp', fmt='WEBP'))

    def test_other_formats_and_non_images_are_refused(self):
        with self.assertRaisesMessage(ImageProblem, 'GIF files are not accepted'):
            process_upload(image_file('a.gif', fmt='GIF', mode='P', color=1))
        with self.assertRaisesMessage(ImageProblem, "isn't a photo we can read"):
            process_upload(SimpleUploadedFile('fake.jpg', b'<?php echo "hi"; ?>', content_type='image/jpeg'))

    def test_too_big_is_refused(self):
        upload = SimpleUploadedFile('big.jpg', b'0' * (3 * 1024 * 1024), content_type='image/jpeg')
        with self.assertRaisesMessage(ImageProblem, 'over 2 MB'):
            process_upload(upload)


@override_settings(MEDIA_ROOT=MEDIA, MAX_UPLOAD_MB=2)
class PhotoManagerTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user('staff', password='pw', is_staff=True)
        self.client.force_login(self.staff)
        self.car = make_car(make_location('nairobi'))
        self.base = f'/dashboard/cars/{self.car.pk}/photos/'

    def upload(self, **kwargs):
        return self.client.post(self.base, {'image': image_file(**kwargs)})

    def test_upload_first_is_cover_then_reorder_cover_delete(self):
        first = self.upload().json()['photo']
        self.assertTrue(first['is_cover'])
        second = self.upload(color=(0, 0, 200)).json()['photo']
        self.assertFalse(second['is_cover'])
        photo = CarPhoto.objects.get(pk=second['id'])
        self.assertEqual(stored_size(photo.thumbnail)[0][0], 600)

        res = self.client.post(f'{self.base}order/', json.dumps({'order': [second['id'], first['id']]}),
                               content_type='application/json')
        self.assertEqual([p['id'] for p in res.json()['photos']], [first['id'], second['id']])  # cover first
        self.assertEqual(CarPhoto.objects.get(pk=second['id']).order, 0)

        self.client.post(f'{self.base}{second["id"]}/cover/')
        self.assertEqual(self.car.cover.pk, second['id'])

        files = [Path(MEDIA) / photo.image.name, Path(MEDIA) / photo.thumbnail.name]
        self.assertTrue(all(f.exists() for f in files))
        with self.captureOnCommitCallbacks(execute=True):
            res = self.client.post(f'{self.base}{second["id"]}/delete/')
        self.assertEqual([p['id'] for p in res.json()['photos']], [first['id']])
        self.assertTrue(CarPhoto.objects.get(pk=first['id']).is_cover)  # cover moves to what's left
        self.assertFalse(any(f.exists() for f in files))

    def test_bad_upload_returns_a_clear_error(self):
        res = self.client.post(self.base, {'image': SimpleUploadedFile('x.txt', b'hello', content_type='text/plain')})
        self.assertEqual(res.status_code, 400)
        self.assertIn('JPEG, PNG or WebP', res.json()['error'])

    def test_deleting_a_car_removes_its_photo_files(self):
        self.upload()
        photo = CarPhoto.objects.get()
        path = Path(MEDIA) / photo.image.name
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(f'/dashboard/cars/{self.car.pk}/delete/')
        self.assertFalse(Car.objects.filter(pk=self.car.pk).exists())
        self.assertFalse(path.exists())

    def test_duplicate_copies_details_and_photos_hidden(self):
        self.car.features = ['bluetooth']
        self.car.weekly_rate = 20000
        self.car.save()
        self.upload()
        res = self.client.post(f'/dashboard/cars/{self.car.pk}/duplicate/')
        copy = Car.objects.exclude(pk=self.car.pk).get()
        self.assertRedirects(res, f'/dashboard/cars/{copy.pk}/edit/')
        self.assertEqual((copy.name, copy.is_active, copy.features, copy.weekly_rate),
                         (f'{self.car.name} (copy)', False, ['bluetooth'], 20000))
        new_photo = copy.photos.get()
        self.assertNotEqual(new_photo.image.name, self.car.photos.get().image.name)
        self.assertTrue((Path(MEDIA) / new_photo.image.name).exists())

    def test_non_staff_and_other_branches_cannot_upload(self):
        self.client.logout()
        self.assertEqual(self.upload().status_code, 302)
        mombasa_staff = User.objects.create_user('m', password='pw', is_staff=True)
        StaffProfile.objects.create(user=mombasa_staff, location=make_location('mombasa'))
        self.client.force_login(mombasa_staff)
        self.assertEqual(self.upload().status_code, 404)
        self.assertFalse(CarPhoto.objects.exists())

    def test_cars_list_shows_upcoming_bookings_and_rates(self):
        from bookings.models import Booking

        start, end = trip()
        Booking.objects.create(car=self.car, customer_name='X', phone='254712345678', pickup_date=start,
                               return_date=end, days=3, amount=1, status=Booking.Status.PAID)
        self.car.weekly_rate = 25000
        self.car.save()
        res = self.client.get('/dashboard/cars/')
        self.assertContains(res, '1 upcoming booking')
        self.assertContains(res, 'KES 25,000/week')

    def test_car_form_rejects_weekly_rate_above_seven_days(self):
        form_data = {'name': 'Axio', 'location': self.car.location_id, 'category': 'saloon',
                     'transmission': 'automatic', 'fuel': 'petrol', 'seats': 5, 'doors': 4, 'luggage': 2,
                     'price_per_day': 4000, 'weekly_rate': 30000, 'units': 1}
        res = self.client.post(f'/dashboard/cars/{self.car.pk}/edit/', form_data)
        self.assertContains(res, 'weekly price should be less than 7 days')


class RatePricingTests(TestCase):
    def setUp(self):
        self.nairobi = make_location('nairobi')
        self.point = make_point(self.nairobi)
        self.car = make_car(self.nairobi, price=4000)
        self.car.weekly_rate = 24500    # KES 3,500 a day
        self.car.monthly_rate = 90000   # KES 3,000 a day
        self.car.save()

    def total(self, days):
        start, end = trip(days=days)
        return quote(self.car, start, end, self.point.pk)

    def test_rates_by_length(self):
        self.assertEqual(daily_rate_for(self.car, 6), (4000, 'daily'))
        self.assertEqual(daily_rate_for(self.car, 7), (3500, 'weekly'))
        self.assertEqual(daily_rate_for(self.car, 29), (3500, 'weekly'))
        self.assertEqual(daily_rate_for(self.car, 30), (3000, 'monthly'))
        self.assertEqual(self.total(10).total, 35000)
        self.assertIn('(weekly rate)', self.total(10).lines()[0]['label'])
        self.assertEqual(self.total(30).total, 90000)

    def test_late_return_can_tip_into_the_weekly_rate(self):
        start, end = trip(days=6)
        q = quote(self.car, start, end, self.point.pk, pickup_time='10:00', return_time='12:00')
        self.assertEqual((q.days, q.rate_type, q.total), (7, 'weekly', 24500))

    def test_without_rates_daily_price_applies(self):
        self.car.weekly_rate = self.car.monthly_rate = None
        self.car.save()
        self.assertEqual(daily_rate_for(self.car, 45), (4000, 'daily'))


@override_settings(MEDIA_ROOT=MEDIA)
class CarPageTests(TestCase):
    def setUp(self):
        self.nairobi = make_location('nairobi')
        self.car = make_car(self.nairobi, name='Toyota Axio', price=4500)
        self.car.features = ['bluetooth', 'reverse_camera']
        self.car.weekly_rate = 28000
        self.car.save()

    def test_page_shows_specs_features_prices_and_booking(self):
        res = self.client.get(self.car.get_absolute_url())
        self.assertEqual(res.status_code, 200)
        for text in ('Toyota Axio', 'Reverse camera', 'KES 4,500', 'KES 4,000', 'KES 28,000 a week',
                     'Choose dates and book', 'id="availability-preview"', 'id="booking-dialog"'):
            self.assertContains(res, text)

    def test_wrong_slug_redirects_and_hidden_cars_404(self):
        res = self.client.get(f'/cars/{self.car.pk}/old-name/')
        self.assertRedirects(res, self.car.get_absolute_url(), status_code=301)
        self.car.is_active = False
        self.car.save()
        self.assertEqual(self.client.get(self.car.get_absolute_url()).status_code, 404)

    def test_gallery_and_card_use_thumbnails(self):
        from fleet.images import save_photo

        save_photo(self.car, image_file(size=(2000, 1250)))
        photo = self.car.photos.get()
        res = self.client.get(self.car.get_absolute_url())
        self.assertContains(res, f'{photo.thumbnail.url} 600w, {photo.image.url} 1600w')
        self.assertContains(res, 'data-full="' + photo.image.url)
        home = self.client.get('/', {'city': 'nairobi'})
        self.assertContains(home, photo.thumbnail.url)
        self.assertContains(home, 'loading="lazy"')

    def test_sitemap_lists_car_pages(self):
        with self.settings(SITE_URL='https://www.zidicarhire.com'):
            xml = self.client.get('/sitemap.xml').content.decode()
        self.assertIn(f'https://www.zidicarhire.com{self.car.get_absolute_url()}', xml)
