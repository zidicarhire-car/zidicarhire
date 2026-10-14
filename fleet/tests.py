import json
from io import StringIO

from django.core.management import call_command
from django.db.models import Count
from django.test import TestCase, override_settings

from bookings.models import Booking
from fleet.models import Location, PickupPoint

from .test_utils import make_car, make_location, make_point, make_route, trip


def book(car, start, end, status=Booking.Status.PAID):
    return Booking.objects.create(
        car=car, customer_name='Someone', phone='254712345678', pickup_location=car.location,
        return_location=car.location, pickup_date=start, return_date=end, days=(end - start).days,
        amount=car.price_per_day * (end - start).days, status=status,
    )


class AvailabilityPerLocationTests(TestCase):
    def setUp(self):
        self.nairobi = make_location('nairobi', latitude='-1.286389', longitude='36.817223')
        self.mombasa = make_location('mombasa', latitude='-4.043477', longitude='39.668206')
        self.nbo_axio = make_car(self.nairobi, price=4000)
        self.mba_axio = make_car(self.mombasa, price=4500)  # same model, separate unit and price
        self.start, self.end = trip()

    def test_booking_one_city_does_not_block_the_same_model_elsewhere(self):
        book(self.nbo_axio, self.start, self.end)
        self.assertFalse(self.nbo_axio.is_available(self.start, self.end))
        self.assertTrue(self.mba_axio.is_available(self.start, self.end))

    def test_availability_api_is_limited_to_the_city(self):
        book(self.nbo_axio, self.start, self.end)
        res = self.client.get('/api/availability/', {'from': self.start, 'to': self.end, 'city': 'mombasa'})
        self.assertEqual(res.json()['available'], {str(self.mba_axio.pk): True})
        res = self.client.get('/api/availability/', {'from': self.start, 'to': self.end, 'city': 'nairobi'})
        self.assertEqual(res.json()['available'], {str(self.nbo_axio.pk): False})

    def test_search_lists_only_cars_in_the_chosen_city_with_prices_for_that_city(self):
        res = self.client.get('/', {'city': 'mombasa', 'from': self.start, 'to': self.end})
        self.assertEqual([c.pk for c in res.context['cars']], [self.mba_axio.pk])
        self.assertContains(res, 'KES 4,500')
        self.assertNotContains(res, 'KES 4,000')

    def test_home_defaults_to_nairobi(self):
        res = self.client.get('/')
        self.assertEqual(res.context['location'], self.nairobi)

    def test_inactive_city_cars_are_hidden(self):
        self.mombasa.is_active = False
        self.mombasa.save()
        res = self.client.get('/', {'city': 'mombasa'})
        self.assertEqual(res.context['location'], self.nairobi)

    def test_suggests_nearest_cities_with_free_cars_when_none_are_free(self):
        nakuru = make_location('nakuru', latitude='-0.303099', longitude='36.080026')
        make_car(nakuru)
        book(self.nbo_axio, self.start, self.end)
        res = self.client.get('/', {'city': 'nairobi', 'from': self.start, 'to': self.end})
        suggested = [loc.slug for loc in res.context['suggestions']]
        self.assertEqual(suggested, ['nakuru', 'mombasa'])  # Nakuru is closer to Nairobi than Mombasa
        self.assertContains(res, 'See cars in Nakuru')
        self.assertContains(res, 'data-open-chat')

    def test_return_options_only_list_active_routes(self):
        kisumu = make_location('kisumu')
        make_route(self.nairobi, self.mombasa, fee=8000)
        make_route(self.nairobi, kisumu, fee=9000, is_active=False)
        res = self.client.get('/', {'city': 'nairobi'})
        routes = res.context['routes_by_city']['nairobi']
        self.assertEqual([r['slug'] for r in routes], ['mombasa'])


class CityPageTests(TestCase):
    def setUp(self):
        self.mombasa = make_location('mombasa', county='Mombasa', address='Moi Avenue', phone='0711000111')
        self.nairobi = make_location('nairobi')
        make_point(self.mombasa, 'Moi International Airport', fee=1000)
        self.car = make_car(self.mombasa, name='Nissan X-Trail')
        make_car(self.nairobi, name='Toyota Vitz')

    @override_settings(SITE_URL='http://localhost:8000')
    def test_city_page_shows_that_city_only(self):
        res = self.client.get('/car-hire/mombasa/')
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, '<title>Car hire in Mombasa')
        self.assertContains(res, 'Nissan X-Trail')
        self.assertNotContains(res, 'Toyota Vitz')
        self.assertContains(res, 'Moi International Airport')
        self.assertContains(res, 'Moi Avenue')
        self.assertContains(res, 'rel="canonical" href="http://localhost:8000/car-hire/mombasa/"')

    def test_custom_seo_text_is_used(self):
        self.mombasa.seo_title = 'Mombasa car rental from KES 3,500'
        self.mombasa.meta_description = 'Coast car hire'
        self.mombasa.intro = 'Hire a car at the coast.'
        self.mombasa.save()
        res = self.client.get('/car-hire/mombasa/')
        self.assertContains(res, '<title>Mombasa car rental from KES 3,500</title>', html=True)
        self.assertContains(res, 'content="Coast car hire"')
        self.assertContains(res, 'Hire a car at the coast.')

    def test_city_pages_have_unique_titles(self):
        a = self.client.get('/car-hire/mombasa/').context['location'].page_title
        b = self.client.get('/car-hire/nairobi/').context['location'].page_title
        self.assertNotEqual(a, b)

    def test_local_business_json_ld(self):
        res = self.client.get('/car-hire/mombasa/')
        html = res.content.decode()
        raw = html.split('<script type="application/ld+json">')[1].split('</script>')[0]
        data = json.loads(raw)
        self.assertEqual(data['@type'], 'AutoRental')
        self.assertEqual(data['address']['addressLocality'], 'Mombasa')
        self.assertEqual(data['telephone'], '0711000111')

    def test_inactive_city_page_is_404(self):
        self.mombasa.is_active = False
        self.mombasa.save()
        self.assertEqual(self.client.get('/car-hire/mombasa/').status_code, 404)

    @override_settings(SITE_URL='https://www.zidicarhire.com')
    def test_sitemap_lists_active_city_pages(self):
        make_location('nanyuki', is_active=False)
        xml = self.client.get('/sitemap.xml').content.decode()
        self.assertIn('<loc>https://www.zidicarhire.com/car-hire/mombasa/</loc>', xml)
        self.assertIn('<loc>https://www.zidicarhire.com/car-hire/nairobi/</loc>', xml)
        self.assertNotIn('nanyuki', xml)

    def test_car_cards_show_city(self):
        res = self.client.get('/', {'city': 'mombasa'})
        self.assertContains(res, 'class="car-city"')
        self.assertContains(res, 'data-city="Mombasa"')

    def test_home_lists_branches(self):
        res = self.client.get('/')
        self.assertContains(res, 'Our branches')
        self.assertContains(res, 'See cars in Mombasa')
        self.assertContains(res, 'href="/car-hire/mombasa/"')


class SeedLocationsTests(TestCase):
    def test_seed_is_safe_to_rerun_and_keeps_edits(self):
        call_command('seed_locations', stdout=StringIO())
        nairobi = Location.objects.get(slug='nairobi')
        nairobi.opening_hours = 'Always open'
        nairobi.save()
        call_command('seed_locations', stdout=StringIO())
        self.assertEqual(Location.objects.get(slug='nairobi').opening_hours, 'Always open')
        self.assertEqual(Location.objects.filter(is_active=True).count(), 5)
        self.assertEqual(set(Location.objects.filter(is_active=False).values_list('slug', flat=True)),
                         {'nanyuki', 'naivasha', 'diani'})
        self.assertTrue(PickupPoint.objects.filter(location__slug='mombasa', name='Moi International Airport').exists())
        duplicates = PickupPoint.objects.values('location', 'name').annotate(n=Count('id')).filter(n__gt=1)
        self.assertFalse(duplicates.exists())
