import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.utils import timezone

from bookings.models import Booking
from chat.models import Conversation
from fleet.models import Car
from fleet.test_utils import make_car, make_location, trip

from .models import StaffProfile

User = get_user_model()


def staff(username, location=None, **kwargs):
    user = User.objects.create_user(username, password='pw', is_staff=True, **kwargs)
    if location is not None:
        StaffProfile.objects.create(user=user, location=location)
    return user


def booking_for(car, status=Booking.Status.PAID, return_location=None, amount=10000):
    start, end = trip()
    return Booking.objects.create(
        car=car, customer_name=f'Customer {car.location.name}', phone='254712345678',
        pickup_location=car.location, return_location=return_location or car.location,
        pickup_date=start, return_date=end, days=3, daily_rate=amount // 3, amount=amount, status=status,
        amount_paid=amount if status in Booking.PAID_STATES else 0,
        paid_at=timezone.now() if status == Booking.Status.PAID else None,
    )


@override_settings(FAKE_PAYMENTS=True)
class BranchStaffTests(TestCase):
    def setUp(self):
        self.nairobi = make_location('nairobi')
        self.mombasa = make_location('mombasa')
        self.nbo_car = make_car(self.nairobi, name='Nairobi Axio')
        self.mba_car = make_car(self.mombasa, name='Mombasa Prado')
        self.nbo_booking = booking_for(self.nbo_car, amount=12000)
        self.mba_booking = booking_for(self.mba_car, amount=30000)
        self.nbo_chat = Conversation.objects.create(name='Nairobi visitor', location=self.nairobi)
        self.mba_chat = Conversation.objects.create(name='Mombasa visitor', location=self.mombasa)
        self.anon_chat = Conversation.objects.create(name='No city visitor')
        self.mombasa_staff = staff('mombasa_staff', self.mombasa)

    def login(self, user):
        self.client.force_login(user)

    def feed(self):
        return self.client.get('/dashboard/api/feed/').json()

    def test_branch_staff_see_only_their_city_bookings_and_stats(self):
        self.login(self.mombasa_staff)
        data = self.feed()
        self.assertEqual([b['ref'] for b in data['bookings']], [self.mba_booking.ref])
        self.assertEqual(data['stats']['revenue_month'], 30000)
        since = self.client.get('/dashboard/api/feed/', {'since': '2000-01-01T00:00:00+00:00'}).json()
        self.assertEqual([b['ref'] for b in since['bookings']], [self.mba_booking.ref])

    def test_branch_staff_cannot_act_on_other_city_bookings(self):
        self.login(self.mombasa_staff)
        res = self.client.post(f'/dashboard/api/bookings/{self.nbo_booking.ref}/action/',
                               json.dumps({'action': 'cancel'}), content_type='application/json')
        self.assertEqual(res.status_code, 404)
        self.nbo_booking.refresh_from_db()
        self.assertEqual(self.nbo_booking.status, Booking.Status.PAID)

    def test_branch_staff_see_one_way_hires_coming_to_them(self):
        incoming = booking_for(self.nbo_car, return_location=self.mombasa)
        self.login(self.mombasa_staff)
        refs = {b['ref'] for b in self.feed()['bookings']}
        self.assertEqual(refs, {self.mba_booking.ref, incoming.ref})

    def test_branch_staff_see_and_manage_only_their_cars(self):
        self.login(self.mombasa_staff)
        res = self.client.get('/dashboard/cars/')
        self.assertContains(res, 'Mombasa Prado')
        self.assertNotContains(res, 'Nairobi Axio')
        self.assertEqual(self.client.get(f'/dashboard/cars/{self.nbo_car.pk}/edit/').status_code, 404)
        self.assertEqual(self.client.post(f'/dashboard/cars/{self.nbo_car.pk}/toggle/').status_code, 404)
        self.assertEqual(self.client.post(f'/dashboard/cars/{self.nbo_car.pk}/delete/').status_code, 404)
        self.assertTrue(Car.objects.get(pk=self.nbo_car.pk).is_active)

    def test_branch_staff_cannot_add_a_car_to_another_city(self):
        self.login(self.mombasa_staff)
        data = {'name': 'Sneaky Vitz', 'location': self.nairobi.pk, 'category': 'compact', 'transmission': 'automatic',
                'fuel': 'petrol', 'seats': 5, 'doors': 4, 'luggage': 2, 'air_con': 'on', 'price_per_day': 3000,
                'units': 1, 'is_active': 'on'}
        self.client.post('/dashboard/cars/', data)
        self.assertFalse(Car.objects.filter(name='Sneaky Vitz').exists())
        data['location'] = self.mombasa.pk
        self.client.post('/dashboard/cars/', data)
        self.assertEqual(Car.objects.get(name='Sneaky Vitz').location, self.mombasa)

    def test_branch_staff_see_only_their_city_chats(self):
        self.login(self.mombasa_staff)
        names = [c['name'] for c in self.client.get('/dashboard/api/chats/').json()['chats']]
        self.assertEqual(names, ['Mombasa visitor'])
        self.assertEqual(self.client.get(f'/dashboard/api/chats/{self.nbo_chat.id}/messages/').status_code, 404)
        res = self.client.post(f'/dashboard/api/chats/{self.nbo_chat.id}/reply/', json.dumps({'body': 'hi'}),
                               content_type='application/json')
        self.assertEqual(res.status_code, 404)

    def test_branch_staff_cannot_manage_branches_or_switch_city(self):
        self.login(self.mombasa_staff)
        self.assertRedirects(self.client.get('/dashboard/branches/'), '/dashboard/')
        self.assertRedirects(self.client.get('/dashboard/routes/'), '/dashboard/')
        self.client.post('/dashboard/city/', {'city': self.nairobi.pk})
        self.assertEqual([b['ref'] for b in self.feed()['bookings']], [self.mba_booking.ref])
        res = self.client.post(f'/dashboard/api/chats/{self.mba_chat.id}/assign/', json.dumps({'city_id': ''}),
                               content_type='application/json')
        self.assertEqual(res.status_code, 403)

    def test_owner_sees_everything_and_can_filter_by_city(self):
        self.login(staff('owner'))
        self.assertEqual(len(self.feed()['bookings']), 2)
        self.assertEqual(len(self.client.get('/dashboard/api/chats/').json()['chats']), 3)
        self.assertEqual(self.client.get('/dashboard/branches/').status_code, 200)

        self.client.post('/dashboard/city/', {'city': self.nairobi.pk})
        data = self.feed()
        self.assertEqual([b['ref'] for b in data['bookings']], [self.nbo_booking.ref])
        self.assertEqual(data['stats']['revenue_month'], 12000)
        self.assertEqual(data['city'], 'nairobi')
        res = self.client.get('/dashboard/cars/')
        self.assertContains(res, 'Nairobi Axio')
        self.assertNotContains(res, 'Mombasa Prado')

        self.client.post('/dashboard/city/', {'city': ''})
        self.assertEqual(self.feed()['stats']['revenue_month'], 42000)

    def test_superuser_with_a_branch_still_sees_everything(self):
        boss = staff('boss', self.mombasa, is_superuser=True)
        self.login(boss)
        self.assertEqual(len(self.feed()['bookings']), 2)

    def test_owner_can_move_a_chat_to_a_branch(self):
        self.login(staff('owner'))
        res = self.client.post(f'/dashboard/api/chats/{self.anon_chat.id}/assign/',
                               json.dumps({'city_id': self.mombasa.pk}), content_type='application/json')
        self.assertEqual(res.json()['city'], 'Mombasa')
        self.login(self.mombasa_staff)
        names = {c['name'] for c in self.client.get('/dashboard/api/chats/').json()['chats']}
        self.assertEqual(names, {'Mombasa visitor', 'No city visitor'})

    def test_relocate_action_moves_car_after_one_way(self):
        one_way = booking_for(self.nbo_car, return_location=self.mombasa)
        self.login(self.mombasa_staff)
        res = self.client.get('/dashboard/cars/')
        self.assertNotContains(res, 'Returning to')  # the car is still listed in Nairobi
        self.login(staff('owner'))
        self.assertContains(self.client.get('/dashboard/cars/'), 'Returning to Mombasa')
        res = self.client.post(f'/dashboard/api/bookings/{one_way.ref}/action/', json.dumps({'action': 'relocate'}),
                               content_type='application/json')
        self.assertEqual(res.status_code, 200)
        self.nbo_car.refresh_from_db()
        self.assertEqual(self.nbo_car.location, self.mombasa)


class ReportsTests(TestCase):
    def test_revenue_and_bookings_per_city_per_month(self):
        nairobi, mombasa = make_location('nairobi'), make_location('mombasa')
        booking_for(make_car(nairobi), amount=10000)
        booking_for(make_car(nairobi, name='Vitz'), amount=5000)
        booking_for(make_car(mombasa), amount=7000)
        booking_for(make_car(mombasa, name='Unpaid'), status=Booking.Status.FAILED, amount=99999)
        self.client.force_login(staff('owner'))
        res = self.client.get('/dashboard/reports/')
        this_month = res.context['rows'][0]
        cities = [c.slug for c in res.context['cities']]
        by_city = dict(zip(cities, this_month['cells']))
        self.assertEqual(by_city['nairobi'], (2, 15000))
        self.assertEqual(by_city['mombasa'], (1, 7000))
        self.assertEqual((this_month['n'], this_month['revenue']), (3, 22000))

        self.client.force_login(staff('mombasa_staff', mombasa))
        res = self.client.get('/dashboard/reports/')
        self.assertEqual([c.slug for c in res.context['cities']], ['mombasa'])
        self.assertEqual(res.context['grand_revenue'], 7000)


class BranchManagementTests(TestCase):
    def setUp(self):
        self.nairobi = make_location('nairobi')
        self.mombasa = make_location('mombasa')
        self.client.force_login(staff('owner'))

    def test_edit_branch_and_add_pickup_point(self):
        data = {
            'name': 'Nairobi', 'slug': 'nairobi', 'city': 'Nairobi', 'county': 'Nairobi', 'address': 'Kenyatta Ave',
            'display_order': 1, 'is_active': 'on',
            'pickup_points-TOTAL_FORMS': 2, 'pickup_points-INITIAL_FORMS': 0,
            'pickup_points-0-name': 'JKIA', 'pickup_points-0-fee': 1500, 'pickup_points-0-display_order': 0,
            'pickup_points-0-is_active': 'on',
            'pickup_points-1-name': '', 'pickup_points-1-fee': 0, 'pickup_points-1-display_order': 0,
            'pickup_points-1-is_active': 'on',
        }
        res = self.client.post(f'/dashboard/branches/{self.nairobi.pk}/', data)
        self.assertEqual(res.status_code, 302, res.context and [res.context['form'].errors, res.context['points'].errors])
        self.nairobi.refresh_from_db()
        self.assertEqual(self.nairobi.address, 'Kenyatta Ave')
        self.assertEqual(list(self.nairobi.pickup_points.values_list('name', 'fee')), [('JKIA', 1500)])

    def routes_post(self, rows):
        data = {'form-TOTAL_FORMS': len(rows), 'form-INITIAL_FORMS': 0}
        for i, (src, dst, fee) in enumerate(rows):
            data.update({f'form-{i}-from_location': src.pk, f'form-{i}-to_location': dst.pk,
                         f'form-{i}-fee': fee, f'form-{i}-is_active': 'on'})
        return self.client.post('/dashboard/routes/', data)

    def test_add_route(self):
        self.assertEqual(self.routes_post([(self.nairobi, self.mombasa, 8000)]).status_code, 302)
        route = self.nairobi.routes_out.get()
        self.assertEqual((route.to_location, route.fee), (self.mombasa, 8000))

    def test_route_to_same_city_is_refused(self):
        res = self.routes_post([(self.nairobi, self.nairobi, 8000)])
        self.assertEqual(res.status_code, 200)
        self.assertContains(res, 'Choose two different cities.')
        self.assertFalse(self.nairobi.routes_out.exists())

    def test_hide_branch(self):
        self.client.post(f'/dashboard/branches/{self.mombasa.pk}/toggle/')
        self.mombasa.refresh_from_db()
        self.assertFalse(self.mombasa.is_active)
