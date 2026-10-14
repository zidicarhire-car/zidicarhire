from django.core.management.base import BaseCommand

from fleet.models import Car, Location

SAMPLE_CARS = [
    dict(name='Toyota Vitz', category='compact', transmission='automatic', fuel='petrol', seats=5,
         price_per_day=3500, units=3, description='Easy to park and light on fuel. Good for getting around town.'),
    dict(name='Toyota Axio', category='saloon', transmission='automatic', fuel='petrol', seats=5,
         price_per_day=4500, units=2, description='Comfortable saloon for business trips and airport runs.'),
    dict(name='Nissan X-Trail', category='suv', transmission='automatic', fuel='petrol', seats=5,
         price_per_day=7000, units=2, description='Roomy SUV with a big boot for family trips upcountry.'),
    dict(name='Toyota Land Cruiser Prado', category='4x4', transmission='automatic', fuel='diesel', seats=7,
         price_per_day=14000, units=1, description='Built for safari roads and long distances. Seats seven.'),
]


class Command(BaseCommand):
    help = 'Adds sample cars to the Nairobi branch so the site is not empty. Safe to run once; skips cars that already exist.'

    def handle(self, *args, **options):
        nairobi, _ = Location.objects.get_or_create(
            slug='nairobi', defaults={'name': 'Nairobi', 'city': 'Nairobi', 'county': 'Nairobi'}
        )
        added = 0
        for data in SAMPLE_CARS:
            _, created = Car.objects.get_or_create(name=data['name'], location=nairobi, defaults=data)
            added += int(created)
        self.stdout.write(self.style.SUCCESS(f'Added {added} sample car(s). Add photos in the dashboard.'))
