from django.core.management.base import BaseCommand
from django.db import transaction

from fleet.models import Location, PickupPoint

DEFAULT_HOURS = 'Mon to Sat 8am to 6pm, Sun 9am to 1pm'

# Fees are starting points in KES. Change them in the dashboard under Branches.
BRANCHES = [
    dict(slug='nairobi', name='Nairobi', city='Nairobi', county='Nairobi', active=True, order=10,
         lat='-1.286389', lng='36.817223', points=[
             ('Nairobi branch office', 0),
             ('JKIA (Jomo Kenyatta International Airport)', 1500),
             ('Wilson Airport', 1000),
             ('Nairobi SGR Terminus, Syokimau', 1500),
             ('Hotel or home delivery in Nairobi', 1000),
         ]),
    dict(slug='mombasa', name='Mombasa', city='Mombasa', county='Mombasa', active=True, order=20,
         lat='-4.043477', lng='39.668206', points=[
             ('Mombasa branch office', 0),
             ('Moi International Airport', 1000),
             ('Mombasa SGR Terminus, Miritini', 1000),
             ('Hotel delivery in Mombasa', 1000),
         ]),
    dict(slug='kisumu', name='Kisumu', city='Kisumu', county='Kisumu', active=True, order=30,
         lat='-0.091702', lng='34.767956', points=[
             ('Kisumu branch office', 0),
             ('Kisumu International Airport', 1000),
             ('Hotel delivery in Kisumu', 800),
         ]),
    dict(slug='nakuru', name='Nakuru', city='Nakuru', county='Nakuru', active=True, order=40,
         lat='-0.303099', lng='36.080026', points=[
             ('Nakuru branch office', 0),
             ('Hotel delivery in Nakuru', 800),
         ]),
    dict(slug='eldoret', name='Eldoret', city='Eldoret', county='Uasin Gishu', active=True, order=50,
         lat='0.514277', lng='35.269779', points=[
             ('Eldoret branch office', 0),
             ('Eldoret International Airport', 1000),
             ('Hotel delivery in Eldoret', 800),
         ]),
    dict(slug='nanyuki', name='Nanyuki', city='Nanyuki', county='Laikipia', active=False, order=60,
         lat='0.016700', lng='37.073900', points=[
             ('Nanyuki branch office', 0),
             ('Nanyuki Airstrip', 1000),
             ('Hotel or lodge delivery near Nanyuki', 1500),
         ]),
    dict(slug='naivasha', name='Naivasha', city='Naivasha', county='Nakuru', active=False, order=70,
         lat='-0.716700', lng='36.433300', points=[
             ('Naivasha branch office', 0),
             ('Hotel or lodge delivery around Lake Naivasha', 1500),
         ]),
    dict(slug='diani', name='Diani / Ukunda', city='Ukunda', county='Kwale', active=False, order=80,
         lat='-4.287500', lng='39.566100', points=[
             ('Diani branch office', 0),
             ('Ukunda Airstrip (Diani)', 1000),
             ('Hotel delivery on Diani Beach', 800),
         ]),
]


class Command(BaseCommand):
    help = ('Adds the ZIDICARHIRE branches and their pick-up points. Safe to run again: it only adds what is '
            "missing and fills blank fields, so it won't undo changes made in the dashboard.")

    @transaction.atomic
    def handle(self, *args, **options):
        added_branches = added_points = 0
        for data in BRANCHES:
            location, created = Location.objects.get_or_create(slug=data['slug'], defaults={
                'name': data['name'], 'city': data['city'], 'county': data['county'],
                'is_active': data['active'], 'display_order': data['order'],
                'opening_hours': DEFAULT_HOURS, 'latitude': data['lat'], 'longitude': data['lng'],
            })
            added_branches += int(created)
            if not created:
                # e.g. the Nairobi branch the migration made: fill gaps only.
                changed = []
                for field, value in (('county', data['county']), ('opening_hours', DEFAULT_HOURS),
                                     ('latitude', data['lat']), ('longitude', data['lng'])):
                    if getattr(location, field) in (None, ''):
                        setattr(location, field, value)
                        changed.append(field)
                if changed:
                    location.save(update_fields=changed)

            for order, (name, fee) in enumerate(data['points']):
                _, point_created = PickupPoint.objects.get_or_create(
                    location=location, name=name, defaults={'fee': fee, 'display_order': order},
                )
                added_points += int(point_created)

        self.stdout.write(self.style.SUCCESS(
            f'Added {added_branches} branch(es) and {added_points} pick-up point(s). '
            'Add each branch address, phone and map link in the dashboard under Branches.'
        ))
