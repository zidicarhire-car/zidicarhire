import json
from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings

from fleet.test_utils import make_car, make_location, make_point, make_route, trip

from .models import Booking
from .pricing import QuoteError, quote
from .services import mark_paid, relocate_car


class PricingTests(TestCase):
    def setUp(self):
        self.nairobi = make_location('nairobi')
        self.mombasa = make_location('mombasa')
        self.kisumu = make_location('kisumu')
        self.office = make_point(self.nairobi, 'Nairobi branch office', fee=0)
        self.jkia = make_point(self.nairobi, 'JKIA', fee=1500)
        self.moi_airport = make_point(self.mombasa, 'Moi International Airport', fee=1000)
        self.car = make_car(self.nairobi, price=4000)
        self.start, self.end = trip(days=3)

    def test_same_city_at_branch_office_is_days_times_price(self):
        q = quote(self.car, self.start, self.end, self.office.pk)
        self.assertEqual(q.total, 12000)
        self.assertEqual(q.one_way_fee, 0)
        self.assertEqual(q.return_location, self.nairobi)

    def test_pickup_point_fee_is_added(self):
        q = quote(self.car, self.start, self.end, self.jkia.pk)
        self.assertEqual((q.pickup_fee, q.total), (1500, 13500))
        self.assertIn({'label': 'Pick-up at JKIA', 'amount': 1500}, q.lines())

    def test_pickup_point_must_belong_to_the_cars_city(self):
        with self.assertRaises(QuoteError) as ctx:
            quote(self.car, self.start, self.end, self.moi_airport.pk)
        self.assertEqual(ctx.exception.field, 'pickup_point')

    def test_hidden_pickup_point_is_rejected(self):
        self.jkia.is_active = False
        self.jkia.save()
        with self.assertRaises(QuoteError):
            quote(self.car, self.start, self.end, self.jkia.pk)

    def test_pickup_point_required_when_the_branch_has_some(self):
        with self.assertRaises(QuoteError):
            quote(self.car, self.start, self.end, None)

    def test_one_way_fee_on_active_route(self):
        make_route(self.nairobi, self.mombasa, fee=8000)
        q = quote(self.car, self.start, self.end, self.jkia.pk, 'mombasa')
        self.assertTrue(q.is_one_way)
        self.assertEqual((q.one_way_fee, q.total), (8000, 12000 + 1500 + 8000))

    def test_one_way_refused_without_a_route(self):
        with self.assertRaises(QuoteError) as ctx:
            quote(self.car, self.start, self.end, self.office.pk, 'kisumu')
        self.assertEqual(ctx.exception.field, 'return_location')

    def test_one_way_refused_on_inactive_route(self):
        make_route(self.nairobi, self.mombasa, fee=8000, is_active=False)
        with self.assertRaises(QuoteError):
            quote(self.car, self.start, self.end, self.office.pk, 'mombasa')

    def test_one_way_refused_when_destination_branch_is_hidden(self):
        make_route(self.nairobi, self.mombasa, fee=8000)
        self.mombasa.is_active = False
        self.mombasa.save()
        with self.assertRaises(QuoteError):
            quote(self.car, self.start, self.end, self.office.pk, 'mombasa')

    def test_route_only_works_in_its_own_direction(self):
        make_route(self.mombasa, self.nairobi, fee=8000)
        with self.assertRaises(QuoteError):
            quote(self.car, self.start, self.end, self.office.pk, 'mombasa')

    def test_returning_to_own_city_has_no_one_way_fee(self):
        q = quote(self.car, self.start, self.end, self.office.pk, 'nairobi')
        self.assertFalse(q.is_one_way)
        self.assertEqual(q.one_way_fee, 0)

    def test_quote_endpoint(self):
        make_route(self.nairobi, self.mombasa, fee=8000)
        res = self.client.get('/bookings/quote/', {
            'car_id': self.car.pk, 'from': self.start, 'to': self.end,
            'pickup_point': self.jkia.pk, 'return_location': 'mombasa',
        })
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['quote']['total'], 21500)
        res = self.client.get('/bookings/quote/', {
            'car_id': self.car.pk, 'from': self.start, 'to': self.end,
            'pickup_point': self.jkia.pk, 'return_location': 'kisumu',
        })
        self.assertEqual(res.status_code, 400)


@override_settings(FAKE_PAYMENTS=True, ADMIN_NOTIFY_EMAILS=['owner@example.com'])
class CreateBookingTests(TestCase):
    def setUp(self):
        self.nairobi = make_location('nairobi', notify_email='nairobi@example.com')
        self.mombasa = make_location('mombasa', notify_email='mombasa@example.com')
        self.jkia = make_point(self.nairobi, 'JKIA', fee=1500)
        make_point(self.mombasa, 'Moi International Airport', fee=1000)
        self.route = make_route(self.nairobi, self.mombasa, fee=8000)
        self.car = make_car(self.nairobi, price=4000)
        self.start, self.end = trip(days=3)

    def post(self, **overrides):
        data = {
            'car_id': self.car.pk, 'name': 'Wanjiku Kamau', 'phone': '0712345678', 'email': 'w@example.com',
            'id_number': '12345678', 'licence_number': 'DL-0012345',
            'pickup_location': 'nairobi', 'pickup_point': self.jkia.pk, 'return_location': '',
            'pickup_date': self.start.isoformat(), 'return_date': self.end.isoformat(),
        }
        data.update(overrides)
        with mock.patch('bookings.views.rate_limited', return_value=False):
            return self.client.post('/bookings/create/', json.dumps(data), content_type='application/json')

    def test_total_is_worked_out_on_the_server(self):
        res = self.post(amount=1, total=1, price_per_day=1, pickup_fee=0, one_way_fee=0, return_location='mombasa')
        self.assertEqual(res.status_code, 201, res.content)
        booking = Booking.objects.get()
        self.assertEqual(booking.amount, 3 * 4000 + 1500 + 8000)
        self.assertEqual((booking.daily_rate, booking.pickup_fee, booking.one_way_fee), (4000, 1500, 8000))
        self.assertEqual(booking.pickup_location, self.nairobi)
        self.assertEqual(booking.return_location, self.mombasa)
        self.assertEqual(res.json()['booking']['amount'], 21500)
        self.assertEqual(res.json()['booking']['breakdown'][-1], {'label': 'Total', 'amount': 21500, 'total': True})

    def test_stk_push_is_sent_the_full_total(self):
        with mock.patch('payments.payhero.stk_push', return_value={'reference': 'R1', 'CheckoutRequestID': 'C1'}) as push:
            self.post(return_location='mombasa')
        self.assertEqual(push.call_args.kwargs['amount'], 21500)

    def test_fee_changes_after_booking_do_not_alter_it(self):
        self.post()
        self.jkia.fee = 5000
        self.jkia.save()
        self.car.price_per_day = 9000
        self.car.save()
        booking = Booking.objects.get()
        self.assertEqual(booking.amount, 13500)
        self.assertEqual(booking.price_lines()[-1]['amount'], 13500)

    def test_car_can_only_be_booked_from_its_own_city(self):
        res = self.post(pickup_location='mombasa')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(Booking.objects.count(), 0)

    def test_one_way_needs_an_active_route(self):
        self.route.is_active = False
        self.route.save()
        res = self.post(return_location='mombasa')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()['field'], 'return_location')
        self.assertEqual(Booking.objects.count(), 0)

    def test_car_in_hidden_branch_cannot_be_booked(self):
        self.nairobi.is_active = False
        self.nairobi.save()
        self.assertEqual(self.post().status_code, 404)

    def test_availability_is_per_car(self):
        self.assertEqual(self.post().status_code, 201)
        self.assertEqual(self.post().status_code, 409)  # the only unit is now held
        other = make_car(self.mombasa, price=4500)
        res = self.post(car_id=other.pk, pickup_location='mombasa', pickup_point='')
        self.assertEqual(res.status_code, 400)  # Mombasa needs its own pick-up point...
        point = other.location.pickup_points.get()
        self.assertEqual(self.post(car_id=other.pk, pickup_location='mombasa', pickup_point=point.pk).status_code, 201)

    def test_paid_emails_include_city_point_and_go_to_branches(self):
        self.post(return_location='mombasa')
        booking = Booking.objects.get()
        mail.outbox.clear()
        mark_paid(booking.pk, receipt='QWE123')
        admin_mail = mail.outbox[0]
        self.assertEqual(set(admin_mail.to), {'owner@example.com', 'nairobi@example.com', 'mombasa@example.com'})
        self.assertIn('City: Nairobi', admin_mail.body)
        self.assertIn('Pick-up point: JKIA', admin_mail.body)
        self.assertIn('Return to: Mombasa (one-way)', admin_mail.body)
        self.assertIn('(Nairobi, JKIA)', admin_mail.subject)
        self.assertEqual(mail.outbox[1].to, ['w@example.com'])

    def test_paying_for_one_way_does_not_move_the_car(self):
        self.post(return_location='mombasa')
        booking = Booking.objects.get()
        booking, _ = mark_paid(booking.pk, receipt='QWE123')
        self.car.refresh_from_db()
        self.assertEqual(self.car.location, self.nairobi)
        self.assertTrue(booking.awaiting_relocation)

        booking, moved = relocate_car(booking)
        self.assertTrue(moved)
        self.car.refresh_from_db()
        self.assertEqual(self.car.location, self.mombasa)
        self.assertFalse(booking.awaiting_relocation)
        self.assertFalse(relocate_car(booking)[1])

    def test_receipt_shows_breakdown(self):
        self.post(return_location='mombasa')
        booking = Booking.objects.get()
        res = self.client.get(f'/bookings/{booking.ref}/')
        self.assertContains(res, 'Pick-up at JKIA')
        self.assertContains(res, 'One-way return to Mombasa')
        self.assertContains(res, 'KES 21,500')
