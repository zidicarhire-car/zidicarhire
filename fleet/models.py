import math
import re
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils.text import slugify


class LocationQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class Location(models.Model):
    """A branch in one city. Each car belongs to one branch and is hired out from there."""
    name = models.CharField(max_length=80, help_text='Shown to customers, e.g. "Nairobi" or "Diani / Ukunda"')
    slug = models.SlugField(max_length=80, unique=True, help_text='Used in the city page address: /car-hire/<slug>/')
    city = models.CharField(max_length=80)
    county = models.CharField(max_length=80, blank=True)
    address = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=20, blank=True, help_text='Leave blank to show the main business number')
    whatsapp = models.CharField(max_length=20, blank=True, help_text='WhatsApp number, e.g. 0712 345 678')
    opening_hours = models.CharField(max_length=200, blank=True, help_text='e.g. Mon to Sat 8am to 6pm, Sun 9am to 1pm')
    maps_url = models.URLField(max_length=500, blank=True, verbose_name='Google Maps link')
    notify_email = models.EmailField(
        blank=True, help_text='This branch also gets paid-booking and chat alerts here (on top of ADMIN_NOTIFY_EMAILS)'
    )
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True,
                                   help_text='Used to suggest the nearest branch')
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    seo_title = models.CharField(max_length=70, blank=True, verbose_name='City page title',
                                 help_text='Leave blank for an automatic title')
    meta_description = models.CharField(max_length=170, blank=True, verbose_name='City page meta description',
                                        help_text='Shown in Google results. Leave blank for an automatic one')
    intro = models.TextField(blank=True, verbose_name='City page intro',
                             help_text='A short paragraph at the top of the city page. Leave blank for an automatic one')
    is_active = models.BooleanField(default=True, help_text='Show this branch and its cars on the website')
    display_order = models.PositiveSmallIntegerField(default=0, help_text='Lower numbers show first')

    objects = LocationQuerySet.as_manager()

    class Meta:
        ordering = ['display_order', 'name']

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse('fleet:city', args=[self.slug])

    @property
    def page_title(self):
        return self.seo_title or f'Car hire in {self.name} | Pay with M-Pesa | ZIDICARHIRE'

    @property
    def page_description(self):
        if self.meta_description:
            return self.meta_description
        where = f'{self.name}, {self.county} County' if self.county and self.county != self.name else self.name
        return (f'Hire a car in {where} from the ZIDICARHIRE {self.name} branch. '
                'Saloons, SUVs and 4x4s. Book online and pay instantly with M-Pesa.')

    @property
    def page_intro(self):
        if self.intro:
            return self.intro
        return (f'Pick up your hire car from our {self.name} branch. Choose your dates, see the cars that are free, '
                'and confirm instantly with an M-Pesa payment.')

    @property
    def contact_phone(self):
        return self.phone or settings.BUSINESS['phone']

    @property
    def whatsapp_link(self):
        digits = re.sub(r'\D', '', self.whatsapp)
        if digits.startswith('0'):
            digits = '254' + digits[1:]
        return f'https://wa.me/{digits}' if len(digits) >= 11 else ''

    def distance_km(self, other):
        """Straight-line distance, or None if either branch has no coordinates."""
        if None in (self.latitude, self.longitude, other.latitude, other.longitude):
            return None
        lat1, lon1, lat2, lon2 = map(math.radians, map(float, (self.latitude, self.longitude,
                                                               other.latitude, other.longitude)))
        a = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
        return 6371 * 2 * math.asin(math.sqrt(a))

    def one_way_routes(self):
        """Active routes customers can book from this branch."""
        return (self.routes_out.filter(is_active=True, to_location__is_active=True)
                .select_related('to_location').order_by('to_location__display_order', 'to_location__name'))


class PickupPoint(models.Model):
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='pickup_points')
    name = models.CharField(max_length=120, help_text='e.g. "JKIA", "City centre office", "Hotel delivery"')
    fee = models.PositiveIntegerField(default=0, help_text='Extra charge in KES (0 for the branch office)')
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['display_order', 'fee', 'name']

    def __str__(self):
        return f'{self.location.name}: {self.name}'


class OneWayRoute(models.Model):
    """Customers can only return a car to another city on a route set up here."""
    from_location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='routes_out')
    to_location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='routes_in')
    fee = models.PositiveIntegerField(help_text='One-way fee in KES')
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['from_location__display_order', 'from_location__name', 'to_location__name']
        constraints = [
            models.UniqueConstraint(fields=['from_location', 'to_location'], name='unique_one_way_route'),
        ]

    def __str__(self):
        return f'{self.from_location} to {self.to_location}'

    def clean(self):
        if self.from_location_id and self.from_location_id == self.to_location_id:
            raise ValidationError('Choose two different cities.')


class ExtraQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)


class Extra(models.Model):
    """Optional add-ons customers can tick when booking, e.g. a child seat or an extra driver."""
    name = models.CharField(max_length=80)
    description = models.CharField(max_length=200, blank=True)
    price = models.PositiveIntegerField(help_text='Price in KES')
    per_day = models.BooleanField(default=True, help_text='Charge this price for every day of the hire')
    is_active = models.BooleanField(default=True, help_text='Offer this extra when booking')
    display_order = models.PositiveSmallIntegerField(default=0)

    objects = ExtraQuerySet.as_manager()

    class Meta:
        ordering = ['display_order', 'name']

    def __str__(self):
        return self.name

    def cost(self, days):
        return self.price * days if self.per_day else self.price


class Car(models.Model):
    class Category(models.TextChoices):
        COMPACT = 'compact', 'Compact'
        SALOON = 'saloon', 'Saloon'
        SUV = 'suv', 'SUV'
        FOUR_BY_FOUR = '4x4', '4x4 / Safari'
        VAN = 'van', 'Van / Minibus'
        PICKUP = 'pickup', 'Pickup'
        LUXURY = 'luxury', 'Luxury'

    class Transmission(models.TextChoices):
        AUTOMATIC = 'automatic', 'Automatic'
        MANUAL = 'manual', 'Manual'

    class Fuel(models.TextChoices):
        PETROL = 'petrol', 'Petrol'
        DIESEL = 'diesel', 'Diesel'
        HYBRID = 'hybrid', 'Hybrid'
        ELECTRIC = 'electric', 'Electric'

    name = models.CharField(max_length=120)
    location = models.ForeignKey(Location, on_delete=models.PROTECT, related_name='cars',
                                 help_text='The branch this car is hired out from')
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.SALOON)
    transmission = models.CharField(max_length=20, choices=Transmission.choices, default=Transmission.AUTOMATIC)
    fuel = models.CharField(max_length=20, choices=Fuel.choices, default=Fuel.PETROL)
    FEATURES = [
        ('bluetooth', 'Bluetooth audio'),
        ('usb', 'USB charging'),
        ('carplay', 'Apple CarPlay / Android Auto'),
        ('reverse_camera', 'Reverse camera'),
        ('parking_sensors', 'Parking sensors'),
        ('gps', 'Built-in GPS'),
        ('cruise', 'Cruise control'),
        ('four_wd', '4-wheel drive'),
        ('roof_rack', 'Roof rack'),
        ('sunroof', 'Sunroof'),
        ('child_seat', 'Child seat fittings (ISOFIX)'),
        ('tracker', 'GPS tracker for your safety'),
    ]

    seats = models.PositiveSmallIntegerField(default=5)
    doors = models.PositiveSmallIntegerField(default=4)
    luggage = models.PositiveSmallIntegerField(default=2, help_text='Number of large bags that fit')
    engine_size = models.CharField(max_length=20, blank=True, help_text='e.g. 1500 cc or 2.8 L')
    air_con = models.BooleanField(default=True, verbose_name='Air conditioning')
    price_per_day = models.PositiveIntegerField(help_text='Hire price per day in KES')
    weekly_rate = models.PositiveIntegerField(
        null=True, blank=True, help_text='Optional: price for 7 days in KES, used for hires of 7 days or more')
    monthly_rate = models.PositiveIntegerField(
        null=True, blank=True, help_text='Optional: price for 30 days in KES, used for hires of 30 days or more')
    min_booking_fee = models.PositiveIntegerField(
        null=True, blank=True,
        help_text='Optional: the least a customer can pay to book this car, in KES. Blank = the default from .env')
    units = models.PositiveSmallIntegerField(default=1, help_text='How many of this car you have for hire')
    description = models.TextField(blank=True)
    features = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True, help_text='Show this car on the website')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['price_per_day', 'name']

    def __str__(self):
        return self.name

    @property
    def slug(self):
        return slugify(f'{self.name} {self.location.name}' if self.location_id else self.name) or 'car'

    def get_absolute_url(self):
        return reverse('fleet:car', args=[self.pk, self.slug])

    @property
    def feature_labels(self):
        labels = dict(self.FEATURES)
        return [labels[key] for key in self.features or [] if key in labels]

    @property
    def cover(self):
        """The cover photo, or the first photo. Uses prefetched photos when available."""
        photos = list(self.photos.all())
        return next((p for p in photos if p.is_cover), photos[0] if photos else None)

    @property
    def booking_fee(self):
        """Smallest amount that books this car; the rest is paid at pick-up."""
        return self.min_booking_fee or settings.BOOKING_MIN_FEE

    @property
    def weekly_daily_rate(self):
        return round(self.weekly_rate / 7) if self.weekly_rate else None

    @property
    def monthly_daily_rate(self):
        return round(self.monthly_rate / 30) if self.monthly_rate else None

    def units_booked(self, start, end, exclude=None):
        """Number of this car already taken between start and end (end = return date)."""
        from bookings.models import Booking

        qs = Booking.objects.blocking().filter(car=self, pickup_date__lt=end, return_date__gt=start)
        if exclude is not None:
            qs = qs.exclude(pk=exclude.pk)
        return qs.count()

    def is_available(self, start, end, exclude=None):
        return self.units_booked(start, end, exclude=exclude) < self.units

    def unavailable_dates(self, start, end, exclude=None):
        """
        Days in [start, end) when every unit of this car is out. A booking holds the car from its
        pick-up date up to (not including) its return date, so the car can go out again on the day
        it comes back. Unpaid bookings count while they're inside the payment hold.
        """
        from bookings.models import Booking

        taken = {}
        qs = Booking.objects.blocking().filter(car=self, pickup_date__lt=end, return_date__gt=start)
        if exclude is not None:
            qs = qs.exclude(pk=exclude.pk)
        for pickup, ret in qs.values_list('pickup_date', 'return_date'):
            day = max(pickup, start)
            while day < min(ret, end):
                taken[day] = taken.get(day, 0) + 1
                day += timedelta(days=1)
        return sorted(day for day, count in taken.items() if count >= self.units)


class CarPhoto(models.Model):
    """One photo of a car: a web-sized copy (max 1600px wide) and a 600px thumbnail, both JPEG."""
    car = models.ForeignKey(Car, on_delete=models.CASCADE, related_name='photos')
    image = models.ImageField(upload_to='cars/')
    thumbnail = models.ImageField(upload_to='cars/thumbs/')
    width = models.PositiveIntegerField(default=0)
    height = models.PositiveIntegerField(default=0)
    order = models.PositiveSmallIntegerField(default=0)
    is_cover = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_cover', 'order', 'id']

    def __str__(self):
        return f'{self.car.name} photo {self.pk}'

    def as_dict(self):
        return {'id': self.pk, 'url': self.image.url, 'thumb': self.thumbnail.url, 'is_cover': self.is_cover,
                'order': self.order}
