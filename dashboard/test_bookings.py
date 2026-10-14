"""Managing bookings in the dashboard: list, search, CSV, actions, permissions, calendar."""
import csv
import io
from datetime import time, timedelta

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from bookings.models import Booking, BookingEvent
from fleet.test_utils import make_car, make_location

from .models import StaffProfile

User = get_user_model()


def book(car, start_in=5, days=3, status=Booking.Status.PAID, **kwargs):
    start = timezone.localdate() + timedelta(days=start_in)
    paid = status in Booking.PAID_STATES
    defaults = dict(
        car=car, customer_name='Achieng Otieno', phone='254712345678', email='a@example.com',
        id_number='12345678', licence_number='DL12345', pickup_location=car.location, return_location=car.location,
        pickup_date=start, return_date=start + timedelta(days=days), days=days, daily_rate=4000,
        amount=4000 * days, amount_paid=4000 * days if paid else 0, status=status,
        paid_at=timezone.now() if paid else None, payment_requested_at=timezone.now(),
    )
    defaults.update(kwargs)
    return Booking.objects.create(**defaults)


class PermissionTests(TestCase):
    def setUp(self):
        self.car = make_car(make_location('nairobi'))
        self.booking = book(self.car)

    def test_non_staff_are_blocked_everywhere(self):
        customer = User.objects.create_user('customer', password='pw')
        urls = ['/dashboard/', '/dashboard/bookings/', f'/dashboard/bookings/{self.booking.ref}/',
                '/dashboard/bookings/?export=csv', '/dashboard/calendar/', '/dashboard/cars/',
                f'/dashboard/bookings/{self.booking.ref}/receipt.pdf', '/dashboard/reports/']
        for client_user in (None, customer):
            if client_user:
                self.client.force_login(client_user)
            for url in urls:
                with self.subTest(url=url, user=client_user):
                    res = self.client.get(url)
                    self.assertEqual(res.status_code, 302)
                    self.assertIn('/dashboard/login/', res.url)
            res = self.client.post(f'/dashboard/bookings/{self.booking.ref}/', {'action': 'cancel', 'reason': 'x' * 5})
            self.assertEqual(res.status_code, 302)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.PAID)
        self.assertEqual(self.client.get('/dashboard/api/feed/').status_code, 401)

    def test_branch_staff_cannot_open_another_citys_booking(self):
        mombasa_staff = User.objects.create_user('m', password='pw', is_staff=True)
        StaffProfile.objects.create(user=mombasa_staff, location=make_location('mombasa'))
        self.client.force_login(mombasa_staff)
        self.assertEqual(self.client.get(f'/dashboard/bookings/{self.booking.ref}/').status_code, 404)
        res = self.client.post(f'/dashboard/bookings/{self.booking.ref}/', {'action': 'pickup'})
        self.assertEqual(res.status_code, 404)
        self.assertEqual(self.client.get(f'/dashboard/bookings/{self.booking.ref}/receipt.pdf').status_code, 404)


class BookingListTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user('staff', password='pw', is_staff=True)
        self.client.force_login(self.staff)
        nairobi = make_location('nairobi')
        self.axio = make_car(nairobi, name='Toyota Axio')
        self.prado = make_car(nairobi, name='Land Cruiser Prado', units=3)
        self.a = book(self.axio, start_in=5, customer_name='Achieng Otieno', mpesa_receipt='SJK1ABC2DE')
        self.b = book(self.prado, start_in=20, customer_name='Brian Kiprop', phone='254798765432',
                      status=Booking.Status.FAILED)
        self.c = book(self.prado, start_in=40, customer_name='=HYPERLINK("x")', status=Booking.Status.PENDING)

    def refs(self, **params):
        res = self.client.get('/dashboard/bookings/', params)
        self.assertEqual(res.status_code, 200)
        return [b.ref for b in res.context['page']]

    def test_search_by_ref_name_phone_and_mpesa_code(self):
        self.assertEqual(self.refs(q=self.a.ref.lower()), [self.a.ref])
        self.assertEqual(self.refs(q='kiprop'), [self.b.ref])
        self.assertEqual(self.refs(q='0798 765'), [self.b.ref])
        self.assertEqual(self.refs(q='sjk1abc'), [self.a.ref])

    def test_filters_and_sort(self):
        self.assertEqual(self.refs(status='failed'), [self.b.ref])
        self.assertEqual(set(self.refs(car=self.prado.pk)), {self.b.ref, self.c.ref})
        start = timezone.localdate() + timedelta(days=19)
        self.assertEqual(self.refs(**{'from': start.isoformat(), 'to': (start + timedelta(days=3)).isoformat()}),
                         [self.b.ref])
        self.assertEqual(self.refs(sort='pickup'), [self.a.ref, self.b.ref, self.c.ref])

    def test_pagination(self):
        for i in range(30):
            book(self.prado, start_in=60 + i * 4, status=Booking.Status.CANCELLED)
        res = self.client.get('/dashboard/bookings/')
        self.assertEqual(len(res.context['page']), 25)
        self.assertEqual(len(self.client.get('/dashboard/bookings/', {'page': 2}).context['page']), 8)

    def test_csv_export_uses_filters_and_neutralises_formulas(self):
        res = self.client.get('/dashboard/bookings/', {'export': 'csv', 'car': self.prado.pk})
        self.assertEqual(res['Content-Type'], 'text/csv; charset=utf-8')
        rows = list(csv.reader(io.StringIO(res.content.decode('utf-8-sig'))))
        self.assertEqual(rows[0][0], 'Booking')
        self.assertEqual(len(rows), 3)
        self.assertIn("'=HYPERLINK", ''.join(r[3] for r in rows))

    def test_partial_returns_only_the_table(self):
        res = self.client.get('/dashboard/bookings/', {'partial': 1})
        self.assertNotContains(res, '<html')
        self.assertContains(res, self.a.ref)


@override_settings(ADMIN_NOTIFY_EMAILS=['owner@example.com'])
class BookingActionTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user('wanjiru', password='pw', is_staff=True, first_name='Wanjiru')
        self.client.force_login(self.staff)
        self.car = make_car(make_location('nairobi'), price=4000)
        self.booking = book(self.car)
        self.url = f'/dashboard/bookings/{self.booking.ref}/'

    def act(self, action, **data):
        res = self.client.post(self.url, {'action': action, **data})
        self.booking.refresh_from_db()
        return res

    def last_event(self):
        return self.booking.events.first()

    def test_detail_page_shows_customer_and_actions(self):
        res = self.client.get(self.url)
        for text in ('Achieng Otieno', 'tel:0712345678', 'https://wa.me/254712345678', 'a@example.com', '12345678',
                     'DL12345', 'Mark picked up', 'Cancel booking', 'Change dates', 'Resend confirmation email'):
            self.assertContains(res, text)

    def test_pickup_then_return_with_timeline(self):
        self.act('pickup')
        self.assertEqual(self.booking.status, Booking.Status.PICKED_UP)
        self.assertEqual((self.last_event().kind, self.last_event().who), (BookingEvent.Kind.PICKED_UP, 'Wanjiru'))
        self.assertFalse(self.car.is_available(self.booking.pickup_date, self.booking.return_date))
        self.act('return')
        self.assertEqual(self.booking.status, Booking.Status.COMPLETED)
        self.assertTrue(self.car.is_available(self.booking.pickup_date, self.booking.return_date))

    def test_cancel_needs_a_reason(self):
        self.act('cancel', reason='')
        self.assertEqual(self.booking.status, Booking.Status.PAID)
        self.act('cancel', reason='Customer changed plans')
        self.assertEqual(self.booking.status, Booking.Status.CANCELLED)
        self.assertIn('Customer changed plans', self.last_event().message)
        self.assertIn('Refund', self.last_event().message)

    def test_mark_paid_needs_an_mpesa_code(self):
        pending = book(self.car, start_in=30, status=Booking.Status.PENDING)
        url = f'/dashboard/bookings/{pending.ref}/'
        self.client.post(url, {'action': 'mark_paid', 'code': ''})
        pending.refresh_from_db()
        self.assertEqual(pending.status, Booking.Status.PENDING)
        self.client.post(url, {'action': 'mark_paid', 'code': 'sjk1abc2de'})
        pending.refresh_from_db()
        self.assertEqual((pending.status, pending.mpesa_receipt), (Booking.Status.PAID, 'SJK1ABC2DE'))
        self.assertEqual(pending.events.first().user, self.staff)

    def test_change_dates_previews_then_applies_and_rechecks_availability(self):
        new_end = self.booking.return_date + timedelta(days=2)
        values = {'pickup_date': self.booking.pickup_date.isoformat(), 'pickup_time': '10:00',
                  'return_date': new_end.isoformat(), 'return_time': '10:00'}
        res = self.act('preview_dates', **values)
        self.assertEqual(res.context['preview']['total'], 5 * 4000)
        self.assertEqual(res.context['preview']['difference'], 2 * 4000)
        self.assertEqual(self.booking.days, 3)  # nothing changed yet
        self.act('change_dates', **values)
        self.assertEqual((self.booking.days, self.booking.amount, self.booking.amount_paid), (5, 20000, 12000))
        self.assertEqual(self.booking.balance, 8000)
        self.assertIn('Customer owes KES 8,000', self.last_event().message)

        book(self.car, start_in=5 + 5, days=2)  # someone books right after
        clash = {**values, 'return_date': (new_end + timedelta(days=2)).isoformat()}
        res = self.act('preview_dates', **clash)
        self.assertIn('booked by someone else', res.context['date_error'])
        self.assertEqual(self.booking.days, 5)

    def test_resend_email_and_note(self):
        mail.outbox.clear()
        self.act('resend')
        self.assertEqual(mail.outbox[0].to, ['a@example.com'])
        self.assertEqual(mail.outbox[0].attachments[0][2], 'application/pdf')
        self.act('note', note='Deliver to Westlands at 9am')
        self.assertEqual((self.last_event().kind, self.last_event().message),
                         (BookingEvent.Kind.NOTE, 'Deliver to Westlands at 9am'))

    def test_actions_not_allowed_for_status_are_refused(self):
        self.act('return')
        self.act('pickup')
        self.assertEqual(self.booking.status, Booking.Status.COMPLETED)


class OverviewAndCalendarTests(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_user('staff', password='pw', is_staff=True))
        self.car = make_car(make_location('nairobi'), name='Toyota Axio', units=2)

    def test_overview_lists_todays_pickups_and_returns(self):
        today_pickup = book(self.car, start_in=0, pickup_time=time(18, 0))
        returning = book(self.car, start_in=-3, days=3, status=Booking.Status.PICKED_UP)
        res = self.client.get('/dashboard/')
        self.assertEqual([b.ref for b in res.context['pickups']], [today_pickup.ref])
        self.assertEqual([b.ref for b in res.context['returns']], [returning.ref])
        self.assertIn(returning.ref, [b.ref for b in res.context['out']])

    def test_calendar_puts_overlapping_units_on_separate_lines(self):
        first = book(self.car, start_in=1, days=4)
        second = book(self.car, start_in=2, days=2)
        res = self.client.get('/dashboard/calendar/', {'days': 7})
        row = res.context['rows'][0]
        self.assertEqual(row['lanes'], 2)
        blocks = {blk['booking'].ref: blk for blk in row['blocks']}
        self.assertEqual((blocks[first.ref]['col'], blocks[first.ref]['span']), (3, 4))
        self.assertNotEqual(blocks[first.ref]['row'], blocks[second.ref]['row'])
        self.assertContains(res, f'/dashboard/bookings/{first.ref}/')
