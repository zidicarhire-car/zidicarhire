"""Booking fee: customers pay any amount from the car's booking fee up to the total now, and the rest at pick-up."""
import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from fleet.test_utils import make_car, make_location, trip
from payments.models import Payment
from payments.tests import LIVE, fake_response, make_booking

from .models import Booking, BookingEvent
from .notifications import booking_details
from .pricing import QuoteError, quote
from .receipts import build_pdf
from .services import ActionError, mark_paid, record_balance_payment, start_payment


@override_settings(BOOKING_MIN_FEE=1000)
class BookingFeeRulesTests(TestCase):
    def setUp(self):
        self.nairobi = make_location('nairobi')
        self.car = make_car(self.nairobi, price=3500)
        self.start, self.end = trip(days=3)

    def q(self, car=None):
        return quote(car or self.car, self.start, self.end, None, None, pickup_time='10:00', return_time='10:00')

    def test_default_fee_comes_from_settings_and_cars_can_raise_it(self):
        self.assertEqual(self.car.booking_fee, 1000)
        prado = make_car(self.nairobi, name='Prado', price=14000, min_booking_fee=5000)
        self.assertEqual(prado.booking_fee, 5000)
        self.assertEqual(self.q(prado).min_pay, 5000)

    def test_fee_never_more_than_the_total(self):
        cheap = make_car(self.nairobi, name='Vitz', price=200, min_booking_fee=5000)
        price = self.q(cheap)
        self.assertEqual((price.total, price.min_pay), (600, 600))

    def test_pay_now_range(self):
        price = self.q()                       # 3 days x 3,500 = 10,500
        self.assertEqual(price.pay_now(''), 10500)          # blank = full total
        self.assertEqual(price.pay_now(None), 10500)
        self.assertEqual(price.pay_now('1000'), 1000)
        self.assertEqual(price.pay_now('KES 4,000'), 4000)
        self.assertEqual(price.pay_now(10500), 10500)
        for bad in ('999', '10501', 'abc', '-5', '1000.50'):
            with self.subTest(value=bad), self.assertRaises(QuoteError) as ctx:
                price.pay_now(bad)
            self.assertEqual(ctx.exception.field, 'pay_now')

    def test_quote_api_reports_the_minimum(self):
        res = self.client.get('/bookings/quote/', {'car_id': self.car.pk, 'from': self.start, 'to': self.end,
                                                   'pickup_time': '10:00', 'return_time': '10:00'})
        self.assertEqual((res.json()['quote']['total'], res.json()['quote']['min_pay']), (10500, 1000))


@override_settings(FAKE_PAYMENTS=True, BOOKING_MIN_FEE=1000)
class BookingFeeFlowTests(TestCase):
    def setUp(self):
        self.car = make_car(make_location('nairobi'), price=3500)
        self.start, self.end = trip(days=3)

    def create(self, **changes):
        data = {'car_id': self.car.pk, 'name': 'Achieng Otieno', 'phone': '0712345678', 'id_number': '12345678',
                'licence_number': 'DL12345', 'pickup_date': self.start.isoformat(),
                'return_date': self.end.isoformat(), 'pickup_time': '10:00', 'return_time': '10:00', **changes}
        with mock.patch('bookings.views.rate_limited', return_value=False):
            return self.client.post('/bookings/create/', json.dumps(data), content_type='application/json')

    def test_customer_pays_the_amount_they_chose(self):
        res = self.create(pay_now='3000')
        self.assertEqual(res.status_code, 201, res.content)
        b = Booking.objects.get()
        self.assertEqual((b.amount, b.pay_now, b.due_now), (10500, 3000, 3000))
        self.assertEqual(b.payments.get().amount, 3000)
        data = res.json()['booking']
        self.assertEqual((data['pay_now'], data['balance']), (3000, 7500))
        self.assertIn('paying KES 3,000 now', b.events.get(kind=BookingEvent.Kind.CREATED).message)

    def test_no_amount_means_full_payment(self):
        self.assertEqual(self.create().status_code, 201)
        b = Booking.objects.get()
        self.assertEqual((b.pay_now, b.due_now), (10500, 10500))

    def test_too_little_is_refused_with_the_field(self):
        res = self.create(pay_now='500')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()['field'], 'pay_now')
        self.assertIn('KES 1,000', res.json()['error'])
        self.assertFalse(Booking.objects.exists())

    def test_more_than_the_total_is_refused(self):
        res = self.create(pay_now='20000')
        self.assertEqual((res.status_code, res.json()['field']), (400, 'pay_now'))

    def test_paid_booking_shows_the_balance_everywhere(self):
        self.create(pay_now='1000')
        b = Booking.objects.get()
        b, _ = mark_paid(b.pk, receipt='SJK1ABC2DE')
        self.assertEqual((b.amount_paid, b.balance, b.balance_at_pickup), (1000, 9500, 9500))
        self.assertTrue(build_pdf(b).startswith(b'%PDF'))
        self.assertIn('Balance due at pick-up: KES 9,500', booking_details(b))
        page = self.client.get(f'/bookings/{b.ref}/')
        self.assertContains(page, 'Balance due at pick-up')

    def test_existing_bookings_count_as_paid_in_full(self):
        old = make_booking(self.car, amount=12000)          # pay_now left at 0, like bookings made before this change
        self.assertEqual((old.due_now, old.balance_at_pickup), (12000, 0))
        old, _ = mark_paid(old.pk)
        self.assertEqual((old.amount_paid, old.balance), (12000, 0))


@override_settings(**LIVE)
class BookingFeePaymentTests(TestCase):
    def setUp(self):
        self.car = make_car(make_location('nairobi'))
        self.booking = make_booking(self.car, amount=12000, pay_now=2000, checkout_request_id='ws_CO_1',
                                    payhero_reference='PH1')
        Payment.objects.create(booking=self.booking, reference=self.booking.ref, amount=2000, phone='254712345678',
                               checkout_request_id='ws_CO_1', payhero_reference='PH1')

    @mock.patch('payments.payhero.requests.post')
    def test_prompt_asks_for_the_booking_fee(self, post):
        post.return_value = fake_response(201, {'success': True, 'reference': 'PH2', 'CheckoutRequestID': 'ws_CO_2'})
        start_payment(self.booking)
        self.assertEqual(post.call_args.kwargs['json']['amount'], 2000)

    def callback(self, amount):
        result = {'ExternalReference': self.booking.ref, 'CheckoutRequestID': 'ws_CO_1', 'ResultCode': 0,
                  'ResultDesc': 'ok', 'MpesaReceiptNumber': 'SJK1ABC2DE', 'Amount': amount, 'Status': 'Success'}
        return self.client.post('/payments/callback/', json.dumps({'status': True, 'response': result}),
                                content_type='application/json')

    @mock.patch('payments.payhero.transaction_status', return_value={'status': 'SUCCESS'})
    def test_callback_for_the_booking_fee_confirms_the_booking(self, _status):
        self.callback(2000)
        self.booking.refresh_from_db()
        self.assertEqual((self.booking.status, self.booking.amount_paid, self.booking.balance),
                         (Booking.Status.PAID, 2000, 10000))

    @mock.patch('payments.payhero.transaction_status', return_value={'status': 'SUCCESS'})
    def test_less_than_the_booking_fee_is_refused(self, _status):
        self.callback(1500)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.FAILED)
        self.assertIn('expected KES 2,000', self.booking.result_desc)


@override_settings(FAKE_PAYMENTS=True)
class BalancePaymentTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user('desk', password='pw', is_staff=True)
        self.car = make_car(make_location('nairobi'))
        booking = make_booking(self.car, amount=12000, pay_now=2000)
        self.booking, _ = mark_paid(booking.pk, receipt='SJK1ABC2DE')

    def test_part_then_rest(self):
        b = record_balance_payment(self.booking, self.staff, '4,000', '')
        self.assertEqual((b.amount_paid, b.balance), (6000, 6000))
        b = record_balance_payment(b, self.staff, '6000', 'sjk9xyz8ab')
        self.assertEqual(b.balance, 0)
        messages = list(b.events.filter(kind=BookingEvent.Kind.BALANCE).values_list('message', flat=True))
        self.assertEqual(len(messages), 2)
        self.assertTrue(any('cash' in m for m in messages))
        self.assertTrue(any('SJK9XYZ8AB' in m and 'Fully paid' in m for m in messages))
        with self.assertRaises(ActionError):
            record_balance_payment(b, self.staff, '1', '')

    def test_bad_amounts_and_codes(self):
        for amount, code in (('0', ''), ('abc', ''), ('10001', ''), ('100', 'bad code')):
            with self.subTest(amount=amount, code=code), self.assertRaises(ActionError):
                record_balance_payment(self.booking, self.staff, amount, code)

    def test_dashboard_action(self):
        self.client.login(username='desk', password='pw')
        url = f'/dashboard/bookings/{self.booking.ref}/'
        page = self.client.get(url)
        self.assertContains(page, 'Record balance payment (KES 10,000 owed)')
        self.assertContains(page, 'Booking fee chosen')
        res = self.client.post(url, {'action': 'balance', 'amount': '10000', 'code': ''}, follow=True)
        self.assertContains(res, 'Payment recorded.')
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.balance, 0)
        self.assertNotContains(self.client.get(url), 'Record balance payment')


class CarFormBookingFeeTests(TestCase):
    def setUp(self):
        get_user_model().objects.create_superuser('owner', 'o@example.com', 'pw')
        self.client.login(username='owner', password='pw')
        self.nairobi = make_location('nairobi')

    def post_car(self, **changes):
        data = {'name': 'Toyota Prado', 'location': self.nairobi.pk, 'category': 'suv', 'transmission': 'automatic',
                'fuel': 'diesel', 'seats': 7, 'doors': 5, 'luggage': 3, 'price_per_day': 14000, 'units': 1,
                'is_active': 'on', **changes}
        return self.client.post('/dashboard/cars/', data)

    def test_staff_set_the_price_and_booking_fee(self):
        page = self.client.get('/dashboard/cars/')
        self.assertContains(page, 'Hire price per day (KES)')
        self.assertContains(page, 'Minimum booking fee (KES, optional)')
        self.post_car(min_booking_fee=5000)
        car = self.nairobi.cars.get(name='Toyota Prado')
        self.assertEqual((car.price_per_day, car.min_booking_fee, car.booking_fee), (14000, 5000, 5000))
        self.assertContains(self.client.get('/dashboard/cars/'), 'Book from KES 5,000')

    def test_blank_fee_uses_the_standard_one(self):
        self.post_car(min_booking_fee='')
        car = self.nairobi.cars.get(name='Toyota Prado')
        self.assertIsNone(car.min_booking_fee)
        self.assertContains(self.client.get(car.get_absolute_url()), 'Book with as little as')
