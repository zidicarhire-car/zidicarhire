"""Booking flow: day counting, times, extras, booked dates and customer details."""
import json
from datetime import time, timedelta
from unittest import mock

from django.test import TestCase, override_settings
from django.utils import timezone

from fleet.models import Extra
from fleet.test_utils import make_car, make_location, make_point, trip

from .models import Booking
from .pricing import QuoteError, count_days, quote, time_choices
from .validation import clean_customer


class DayCountTests(TestCase):
    def test_every_started_24_hours_is_a_day(self):
        start, end = trip(days=3)
        self.assertEqual(count_days(start, time(10, 0), end, time(10, 0)), 3)
        self.assertEqual(count_days(start, time(10, 0), end, time(10, 30)), 4)
        self.assertEqual(count_days(start, time(10, 0), end, time(9, 30)), 3)
        self.assertEqual(count_days(start, time(18, 0), start + timedelta(days=1), time(8, 0)), 1)

    @override_settings(BUSINESS_OPEN_TIME=time(7, 0), BUSINESS_CLOSE_TIME=time(20, 0))
    def test_time_choices_are_half_hours_within_business_hours(self):
        choices = time_choices()
        self.assertEqual(choices[0], time(7, 0))
        self.assertEqual(choices[1], time(7, 30))
        self.assertEqual(choices[-1], time(20, 0))
        self.assertEqual(len(choices), 27)


class QuoteRulesTests(TestCase):
    def setUp(self):
        self.nairobi = make_location('nairobi')
        self.office = make_point(self.nairobi, 'Office', fee=0)
        self.car = make_car(self.nairobi, price=3500)
        self.start, self.end = trip(days=3)

    def q(self, **kwargs):
        return quote(self.car, kwargs.pop('start', self.start), kwargs.pop('end', self.end), self.office.pk, **kwargs)

    def test_late_return_adds_a_day(self):
        self.assertEqual(self.q(pickup_time='10:00', return_time='10:00').total, 3 * 3500)
        later = self.q(pickup_time='10:00', return_time='14:30')
        self.assertEqual((later.days, later.total), (4, 4 * 3500))

    def test_time_outside_business_hours_is_refused(self):
        with self.assertRaises(QuoteError) as ctx:
            self.q(pickup_time='05:00')
        self.assertEqual(ctx.exception.field, 'pickup_time')
        with self.assertRaises(QuoteError):
            self.q(return_time='10:15')  # not on a half hour

    def test_return_must_be_after_pickup(self):
        with self.assertRaises(QuoteError):
            self.q(end=self.start)

    @override_settings(MIN_RENTAL_DAYS=3)
    def test_minimum_days(self):
        with self.assertRaises(QuoteError):
            self.q(end=self.start + timedelta(days=2))
        self.assertEqual(self.q(end=self.start + timedelta(days=3)).days, 3)

    @override_settings(MAX_RENTAL_DAYS=5)
    def test_maximum_days(self):
        with self.assertRaises(QuoteError):
            self.q(end=self.start + timedelta(days=6))

    def test_pickup_in_the_past_is_refused(self):
        today = timezone.localdate()
        with self.assertRaises(QuoteError):
            self.q(start=today - timedelta(days=1), end=today + timedelta(days=2))

    def test_extras_per_day_and_once(self):
        seat = Extra.objects.create(name='Child seat', price=500, per_day=True)
        wifi = Extra.objects.create(name='Wi-Fi router', price=1500, per_day=False)
        result = self.q(extras=[seat.pk, wifi.pk])
        self.assertEqual(result.extras, 3 * 500 + 1500)
        self.assertEqual(result.total, 3 * 3500 + 3000)
        labels = [line['label'] for line in result.lines()]
        self.assertIn('Child seat (KES 500/day)', labels)
        self.assertIn('Wi-Fi router', labels)

    def test_hidden_extra_is_refused(self):
        gone = Extra.objects.create(name='GPS', price=300, is_active=False)
        with self.assertRaises(QuoteError) as ctx:
            self.q(extras=[gone.pk])
        self.assertEqual(ctx.exception.field, 'extras')


class BookedDatesTests(TestCase):
    def setUp(self):
        self.nairobi = make_location('nairobi')
        self.car = make_car(self.nairobi, units=2)
        self.today = timezone.localdate()

    def book(self, start_in, days, status=Booking.Status.PAID, requested_minutes_ago=0):
        start = self.today + timedelta(days=start_in)
        return Booking.objects.create(
            car=self.car, customer_name='X', phone='254712345678', pickup_location=self.nairobi,
            return_location=self.nairobi, pickup_date=start, return_date=start + timedelta(days=days),
            days=days, amount=1000, status=status,
            payment_requested_at=timezone.now() - timedelta(minutes=requested_minutes_ago),
        )

    def unavailable(self):
        res = self.client.get(f'/api/cars/{self.car.pk}/booked-dates/', {'months': 2})
        self.assertEqual(res.status_code, 200)
        return res.json()['unavailable']

    def day(self, n):
        return (self.today + timedelta(days=n)).isoformat()

    def test_a_day_is_unavailable_only_when_every_unit_is_out(self):
        self.book(5, 3)
        self.assertEqual(self.unavailable(), [])  # one of two units still free
        self.book(6, 3)
        self.assertEqual(self.unavailable(), [self.day(6), self.day(7)])

    def test_return_day_is_free_again(self):
        self.car.units = 1
        self.car.save()
        self.book(5, 2)
        self.assertEqual(self.unavailable(), [self.day(5), self.day(6)])

    def test_unpaid_bookings_hold_only_during_the_hold(self):
        self.car.units = 1
        self.car.save()
        self.book(5, 1, status=Booking.Status.PENDING, requested_minutes_ago=2)
        self.book(8, 1, status=Booking.Status.PENDING, requested_minutes_ago=60)
        self.book(10, 1, status=Booking.Status.FAILED)
        self.assertEqual(self.unavailable(), [self.day(5)])

    def test_months_is_capped_and_hidden_cars_404(self):
        res = self.client.get(f'/api/cars/{self.car.pk}/booked-dates/', {'months': 99})
        self.assertEqual(res.status_code, 200)
        self.car.is_active = False
        self.car.save()
        self.assertEqual(self.client.get(f'/api/cars/{self.car.pk}/booked-dates/').status_code, 404)


class CustomerValidationTests(TestCase):
    good = {'name': 'Achieng Otieno', 'phone': '0712 345 678', 'email': '', 'id_number': '12345678',
            'licence_number': 'dl-12345'}

    def check(self, **changes):
        return clean_customer({**self.good, **changes})

    def test_good_details_are_cleaned(self):
        data = self.check(phone='+254 110 123 456', id_number='ak 123456', licence_number='dl 12345')
        self.assertEqual(data['phone'], '254110123456')
        self.assertEqual(data['id_number'], 'AK123456')
        self.assertEqual(data['licence_number'], 'DL12345')

    def test_each_bad_field_is_named(self):
        for field, value in [('name', 'A'), ('phone', '0812345678'), ('email', 'me@'),
                             ('id_number', '12'), ('licence_number', '')]:
            with self.subTest(field=field):
                with self.assertRaises(QuoteError) as ctx:
                    self.check(**{field: value})
                self.assertEqual(ctx.exception.field, field)


@override_settings(FAKE_PAYMENTS=True)
class FlowEndpointTests(TestCase):
    def setUp(self):
        self.nairobi = make_location('nairobi')
        self.point = make_point(self.nairobi, 'Office')
        self.car = make_car(self.nairobi, price=3500)
        self.start, self.end = trip(days=3)
        self.seat = Extra.objects.create(name='Child seat', price=500)

    def create(self, **changes):
        data = {'car_id': self.car.pk, 'name': 'Achieng Otieno', 'phone': '0712345678', 'id_number': '12345678',
                'licence_number': 'DL12345', 'pickup_point': self.point.pk, 'pickup_date': self.start.isoformat(),
                'return_date': self.end.isoformat(), 'pickup_time': '09:00', 'return_time': '11:00',
                'extras': [self.seat.pk], 'days': 1, 'amount': 1, **changes}
        with mock.patch('bookings.views.rate_limited', return_value=False):
            return self.client.post('/bookings/create/', json.dumps(data), content_type='application/json')

    def test_create_stores_times_ids_and_extras_and_ignores_browser_numbers(self):
        res = self.create()
        self.assertEqual(res.status_code, 201, res.content)
        b = Booking.objects.get()
        self.assertEqual((b.pickup_time, b.return_time, b.days), (time(9, 0), time(11, 0), 4))
        self.assertEqual(b.amount, 4 * 3500 + 4 * 500)
        self.assertEqual((b.id_number, b.licence_number), ('12345678', 'DL12345'))
        self.assertEqual([(e.name, e.amount) for e in b.extras.all()], [('Child seat', 2000)])
        self.assertNotIn('id_number', res.json()['booking'])

    def test_missing_licence_is_refused_with_field(self):
        res = self.create(licence_number='')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()['field'], 'licence_number')

    def test_quote_reports_dates_the_car_is_booked(self):
        self.create()
        res = self.client.get('/bookings/quote/', {'car_id': self.car.pk, 'from': self.start, 'to': self.end,
                                                   'pickup_point': self.point.pk})
        self.assertEqual(res.status_code, 409)

    def test_links_only_for_the_browser_that_booked(self):
        ref = self.create().json()['booking']['ref']
        self.assertIn('ics_url', self.client.get(f'/bookings/{ref}/status/').json()['booking'])
        other = self.client_class()
        self.assertNotIn('ics_url', other.get(f'/bookings/{ref}/status/').json()['booking'])

    def test_calendar_file_after_payment(self):
        ref = self.create().json()['booking']['ref']
        Booking.objects.filter(ref=ref).update(status=Booking.Status.PAID)
        res = self.client.get(f'/bookings/{ref}/calendar.ics')
        self.assertEqual(res.status_code, 200)
        body = res.content.decode()
        self.assertIn('BEGIN:VCALENDAR', body)
        self.assertEqual(body.count('BEGIN:VEVENT'), 2)
        self.assertEqual(self.client_class().get(f'/bookings/{ref}/calendar.ics').status_code, 404)
