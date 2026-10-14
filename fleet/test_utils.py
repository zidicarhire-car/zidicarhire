"""Small factories shared by the test suites."""
from datetime import timedelta

from django.utils import timezone

from fleet.models import Car, Location, OneWayRoute, PickupPoint


def make_location(slug, **kwargs):
    """Creates a branch, or resets one already there (the migrations add Nairobi to every database)."""
    defaults = {'name': slug.title(), 'city': slug.title(), 'county': slug.title(), 'is_active': True,
                'latitude': None, 'longitude': None}
    defaults.update(kwargs)
    return Location.objects.update_or_create(slug=slug, defaults=defaults)[0]


def make_point(location, name='Branch office', fee=0, **kwargs):
    return PickupPoint.objects.create(location=location, name=name, fee=fee, **kwargs)


def make_car(location, name='Toyota Axio', price=4000, units=1, **kwargs):
    return Car.objects.create(location=location, name=name, price_per_day=price, units=units, **kwargs)


def make_route(src, dst, fee=8000, **kwargs):
    return OneWayRoute.objects.create(from_location=src, to_location=dst, fee=fee, **kwargs)


def trip(start_in=10, days=3):
    start = timezone.localdate() + timedelta(days=start_in)
    return start, start + timedelta(days=days)
