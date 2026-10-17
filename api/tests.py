"""Mobile app API: customer flow with simulated payments, booking tokens, chat, staff sign-in and actions."""
import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from bookings import tokens
from bookings.models import Booking
from chat.models import Conversation
from dashboard.models import StaffProfile
from fleet.test_utils import make_car, make_location, make_point, trip

from .models import ApiToken

User = get_user_model()
CUSTOMER = {'name': 'Achieng Otieno', 'phone': '0712345678', 'email': 'a@example.com',
            'id_number': '12345678', 'licence_number': 'DL123456'}


class ApiTestCase(TestCase):
    def setUp(self):
        # A phone app sends no CSRF cookie: run every request the way a real one arrives.
        self.client = Client(enforce_csrf_checks=True)
        self.nairobi = make_location('nairobi')
        self.office = make_point(self.nairobi, 'Office', fee=0)
        self.car = make_car(self.nairobi, name='Toyota Axio', price=4500)
        self.start, self.end = trip(days=3)

    def post(self, url, data=None, **headers):
        return self.client.post(url, json.dumps(data or {}), content_type='application/json', headers=headers)

    def book(self, **extra):
        return self.post('/api/v1/bookings/', {
            'car_id': self.car.pk, 'pickup_date': self.start.isoformat(), 'return_date': self.end.isoformat(),
            'pickup_time': '10:00', 'return_time': '10:00', 'pickup_point': self.office.pk, **CUSTOMER, **extra})


class CustomerApiTests(ApiTestCase):
    def test_config_lists_branches_and_booking_rules(self):
        data = self.client.get('/api/v1/config/').json()
        self.assertEqual(data['branches'][0]['slug'], 'nairobi')
        self.assertEqual(data['branches'][0]['pickup_points'][0]['name'], 'Office')
        self.assertIn('10:00', data['booking']['times'])

    def test_cars_for_dates_and_filters(self):
        make_car(self.nairobi, name='Toyota Prado', price=14000, transmission='manual')
        data = self.client.get('/api/v1/cars/', {'city': 'nairobi', 'from': self.start, 'to': self.end,
                                                 'sort': 'price_desc'}).json()
        self.assertEqual([c['name'] for c in data['cars']], ['Toyota Prado', 'Toyota Axio'])
        self.assertEqual(data['cars'][1]['total'], 13500)
        self.assertTrue(data['cars'][1]['available'])
        only_auto = self.client.get('/api/v1/cars/', {'city': 'nairobi', 'transmission': 'automatic'}).json()
        self.assertEqual([c['name'] for c in only_auto['cars']], ['Toyota Axio'])

    def test_car_detail_has_prices_and_booked_days(self):
        data = self.client.get(f'/api/v1/cars/{self.car.pk}/').json()
        self.assertEqual(data['car']['prices'][0]['per_day'], 4500)
        self.assertEqual(data['branch']['slug'], 'nairobi')
        self.assertIsInstance(data['unavailable'], list)

    def test_quote_is_priced_by_the_server(self):
        res = self.client.get('/api/v1/quote/', {'car_id': self.car.pk, 'from': self.start, 'to': self.end,
                                                 'pickup_time': '10:00', 'return_time': '10:00',
                                                 'pickup_point': self.office.pk})
        self.assertEqual(res.json()['quote']['total'], 13500)

    @override_settings(FAKE_PAYMENTS=True)
    def test_full_booking_pays_and_gives_a_token_and_receipt_links(self):
        res = self.book(amount=1)   # any amount sent by the phone is ignored
        self.assertEqual(res.status_code, 201)
        booking = res.json()['booking']
        self.assertEqual(booking['amount'], 13500)
        self.assertEqual(booking['token'], tokens.booking_token(booking['ref']))
        self.assertIn(f"?t={booking['token']}", booking['receipt_url'])
        self.assertTrue(Booking.objects.get(ref=booking['ref']).events.filter(message__startswith='Booked in the app').exists())

        # Fake payments settle about 8 seconds after the prompt: move the clock past that.
        Booking.objects.filter(ref=booking['ref']).update(payment_requested_at=timezone.now() - timedelta(seconds=10))
        status = self.client.get(f"/api/v1/bookings/{booking['ref']}/", headers={'X-Booking-Token': booking['token']})
        self.assertEqual(status.json()['booking']['status'], 'paid')
        self.assertEqual(self.client.get(booking['receipt_url'].replace('http://localhost:8000', '')).status_code, 200)

    def test_booking_needs_its_token(self):
        res = self.book()
        ref = res.json().get('booking', {}).get('ref') or Booking.objects.get().ref
        self.assertEqual(self.client.get(f'/api/v1/bookings/{ref}/').status_code, 403)
        self.assertEqual(self.client.get(f'/api/v1/bookings/{ref}/', {'t': 'wrong'}).status_code, 403)

    def test_errors_name_the_field(self):
        res = self.book(licence_number='')
        self.assertEqual((res.status_code, res.json()['field']), (400, 'licence_number'))

    @override_settings(FAKE_PAYMENTS=True)
    def test_find_by_number_and_phone(self):
        ref = self.book().json()['booking']['ref']
        found = self.post('/api/v1/bookings/find/', {'ref': ref.lower(), 'phone': '+254 712 345 678'})
        self.assertEqual(found.json()['booking']['token'], tokens.booking_token(ref))
        self.assertEqual(self.post('/api/v1/bookings/find/', {'ref': ref, 'phone': '0799999999'}).status_code, 404)

    def test_chat_start_send_and_hand_over(self):
        cid = self.post('/api/v1/chat/', {'name': 'Brian', 'city': 'nairobi'}).json()['id']
        sent = self.post(f'/api/v1/chat/{cid}/send/', {'body': 'What are your prices?'})
        self.assertEqual(sent.status_code, 201)
        self.assertTrue(sent.json()['replies'])
        self.assertTrue(self.post(f'/api/v1/chat/{cid}/agent/').json()['wants_agent'])
        self.assertGreaterEqual(len(self.client.get(f'/api/v1/chat/{cid}/messages/').json()['messages']), 3)


class StaffApiTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.staff = User.objects.create_user('wanjiru', password='pw-123456', is_staff=True, first_name='Wanjiru')

    def login(self, username='wanjiru', password='pw-123456'):
        return self.post('/api/v1/staff/login/', {'username': username, 'password': password, 'device': 'Pixel 8'})

    def auth(self, token):
        return {'Authorization': f'Token {token}'}

    def paid_booking(self):
        return Booking.objects.create(
            car=self.car, customer_name='Achieng Otieno', phone='254712345678', pickup_location=self.nairobi,
            return_location=self.nairobi, pickup_date=self.start, return_date=self.end, days=3, daily_rate=4500,
            amount=13500, amount_paid=13500, status=Booking.Status.PAID, mpesa_receipt='SJK1ABC2DE',
            paid_at=timezone.now())

    def test_sign_in_stores_only_a_hash_and_sign_out_ends_it(self):
        res = self.login()
        self.assertEqual(res.status_code, 201)
        token = res.json()['token']
        self.assertTrue(res.json()['user']['is_owner'])
        self.assertFalse(ApiToken.objects.filter(key_hash=token).exists())
        self.assertEqual(self.client.get('/api/v1/staff/me/', headers=self.auth(token)).status_code, 200)
        self.post('/api/v1/staff/logout/', **self.auth(token))
        self.assertEqual(self.client.get('/api/v1/staff/me/', headers=self.auth(token)).status_code, 401)

    def test_customers_and_wrong_passwords_get_no_token(self):
        User.objects.create_user('customer', password='pw-123456')
        self.assertEqual(self.login('customer').status_code, 400)
        self.assertEqual(self.login(password='nope').status_code, 400)
        self.assertEqual(self.client.get('/api/v1/staff/overview/').status_code, 401)

    def test_unused_tokens_expire(self):
        token = self.login().json()['token']
        ApiToken.objects.update(last_used_at=timezone.now() - timedelta(days=61))
        self.assertEqual(self.client.get('/api/v1/staff/me/', headers=self.auth(token)).status_code, 401)

    def test_overview_detail_and_pickup_action(self):
        booking = self.paid_booking()
        token = self.login().json()['token']
        overview = self.client.get('/api/v1/staff/overview/', headers=self.auth(token)).json()
        self.assertEqual(overview['latest'][0]['ref'], booking.ref)
        detail = self.client.get(f'/api/v1/staff/bookings/{booking.ref}/', headers=self.auth(token)).json()['booking']
        self.assertTrue(detail['allowed']['pickup'])
        done = self.post(f'/api/v1/staff/bookings/{booking.ref}/action/', {'action': 'pickup'}, **self.auth(token))
        self.assertEqual(done.json()['booking']['status'], 'picked_up')
        self.assertEqual(done.json()['booking']['events'][0]['who'], 'Wanjiru')
        bad = self.post(f'/api/v1/staff/bookings/{booking.ref}/action/', {'action': 'pickup'}, **self.auth(token))
        self.assertEqual(bad.status_code, 400)

    def test_branch_staff_only_see_their_branch(self):
        booking = self.paid_booking()
        mombasa = User.objects.create_user('m', password='pw-123456', is_staff=True)
        StaffProfile.objects.create(user=mombasa, location=make_location('mombasa'))
        token = self.login('m').json()['token']
        self.assertEqual(self.client.get(f'/api/v1/staff/bookings/{booking.ref}/', headers=self.auth(token)).status_code, 404)
        self.assertEqual(self.client.get('/api/v1/staff/bookings/', headers=self.auth(token)).json()['total'], 0)

    def test_feed_chats_and_reply_reuse_the_dashboard(self):
        token = self.login().json()['token']
        conv = Conversation.objects.create(name='Brian', location=self.nairobi)
        feed = self.client.get('/api/v1/staff/feed/', headers=self.auth(token)).json()
        self.assertIn('stats', feed)
        self.assertEqual(self.client.get('/api/v1/staff/chats/', headers=self.auth(token)).json()['chats'][0]['name'], 'Brian')
        reply = self.post(f'/api/v1/staff/chats/{conv.id}/reply/', {'body': 'Hello Brian'}, **self.auth(token))
        self.assertEqual(reply.status_code, 201)

    def test_change_dates_preview_then_apply(self):
        booking = self.paid_booking()
        token = self.login().json()['token']
        new_end = (self.end + timedelta(days=2)).isoformat()
        dates = {'pickup_date': self.start.isoformat(), 'pickup_time': '10:00', 'return_date': new_end, 'return_time': '10:00'}
        preview = self.post(f'/api/v1/staff/bookings/{booking.ref}/action/', {'action': 'preview_dates', **dates}, **self.auth(token))
        self.assertEqual(preview.json()['preview']['days'], 5)
        done = self.post(f'/api/v1/staff/bookings/{booking.ref}/action/', {'action': 'change_dates', **dates}, **self.auth(token))
        self.assertEqual(done.json()['booking']['return_date'], new_end)
        self.assertIn('?t=', done.json()['booking']['receipt_url'])

    def test_car_toggle(self):
        token = self.login().json()['token']
        res = self.post(f'/api/v1/staff/cars/{self.car.pk}/toggle/', **self.auth(token))
        self.assertFalse(res.json()['is_active'])
