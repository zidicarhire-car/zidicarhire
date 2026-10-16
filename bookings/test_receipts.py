"""Receipts: who can open them, what's in them, and the Find my booking page."""
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from fleet.test_utils import make_car, make_location, make_point, trip

from .models import Booking
from .notifications import notify_booking_paid
from .receipts import build_pdf
from . import tokens
from .tokens import booking_token


def paid_booking(**kwargs):
    nairobi = make_location('nairobi')
    car = make_car(nairobi, name='Toyota Axio', price=4500)
    start, end = trip(days=3)
    defaults = dict(car=car, customer_name='Achieng Otieno', phone='254712345678', email='a@example.com',
                    pickup_location=nairobi, pickup_point=make_point(nairobi, 'JKIA', fee=1500),
                    return_location=nairobi, pickup_date=start, return_date=end, days=3, daily_rate=4500,
                    pickup_fee=1500, amount=15000, amount_paid=15000, status=Booking.Status.PAID,
                    mpesa_receipt='SJK1ABC2DE', paid_at=timezone.now())
    defaults.update(kwargs)
    return Booking.objects.create(**defaults)


class ReceiptAccessTests(TestCase):
    def setUp(self):
        self.booking = paid_booking()
        self.token = booking_token(self.booking.ref)

    def pdf(self, token=None, client=None):
        url = f'/bookings/{self.booking.ref}/receipt.pdf'
        return (client or self.client).get(url, {'t': token} if token is not None else {})

    def test_valid_token_downloads_a_pdf(self):
        res = self.pdf(self.token)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res['Content-Type'], 'application/pdf')
        self.assertTrue(res.content.startswith(b'%PDF'))
        self.assertIn('attachment', res['Content-Disposition'])

    def test_invalid_or_missing_token_is_refused(self):
        self.assertEqual(self.pdf('not-the-token').status_code, 403)
        self.assertEqual(self.pdf().status_code, 403)
        other = paid_booking(customer_name='Someone else')
        self.assertEqual(self.pdf(booking_token(other.ref)).status_code, 403)

    def test_unpaid_booking_has_no_receipt(self):
        Booking.objects.filter(pk=self.booking.pk).update(status=Booking.Status.PENDING)
        res = self.pdf(self.token)
        self.assertEqual(res.status_code, 409)
        self.assertContains(res, "There's no receipt for this booking yet", status_code=409)

    def test_staff_can_download_any_receipt(self):
        staff = get_user_model().objects.create_user('staff', password='pw', is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.pdf().status_code, 200)
        res = self.client.get(f'/dashboard/bookings/{self.booking.ref}/receipt.pdf')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.content.startswith(b'%PDF'))

    def test_signed_link_opens_the_booking_and_printable_receipt(self):
        res = self.client.get(f'/bookings/{self.booking.ref}/', {'t': self.token})
        self.assertContains(res, 'Download receipt (PDF)')
        self.assertContains(res, 'Achieng Otieno')
        page = self.client.get(f'/bookings/{self.booking.ref}/receipt/')  # remembered from the link above
        self.assertContains(page, 'SJK1ABC2DE')
        self.assertContains(page, '0712 *** 678')
        self.assertContains(page, 'Print this receipt')

    def test_booking_page_without_access_hides_personal_details(self):
        res = self.client.get(f'/bookings/{self.booking.ref}/')
        self.assertNotContains(res, 'Achieng Otieno')
        self.assertNotContains(res, 'Download receipt')
        self.assertContains(res, 'find your booking')


@override_settings(BUSINESS={'name': 'ZIDICARHIRE', 'phone': '+254700111222', 'whatsapp': '', 'email': 'b@x.com',
                             'address': 'Moi Avenue, Nairobi', 'location': 'Nairobi', 'kra_pin': 'P051234567X',
                             'till_number': '123456', 'till_name': 'ZIDICARHIRE'})
class ReceiptContentTests(TestCase):
    def test_pdf_contains_the_receipt_details(self):
        booking = paid_booking()
        booking.pickup_location.address = 'Kenyatta Avenue'   # receipts show the Nairobi branch address
        booking.pickup_location.save()
        pdf = build_pdf(booking)
        self.assertTrue(pdf.startswith(b'%PDF'))
        # ReportLab compresses page streams; check the text via the uncompressed version.
        with mock.patch('reportlab.rl_config.pageCompression', 0):
            raw = build_pdf(booking).decode('latin-1')
        for text in ('RECEIPT', booking.ref, 'SJK1ABC2DE', 'KRA PIN P051234567X', 'M-Pesa till 123456',
                     'Kenyatta Avenue, Nairobi', '0712 *** 678', 'Toyota Axio', 'Pick-up at JKIA', 'KES 15,000', 'PAID',
                     'Thank you for hiring'):
            self.assertIn(text, raw)
        self.assertNotIn('254712345678', raw)
        self.assertNotIn('Moi Avenue', raw)   # BUSINESS_ADDRESS is only the fallback

    def test_printable_receipt_shows_the_nairobi_branch_address(self):
        booking = paid_booking()
        booking.pickup_location.address = 'Kenyatta Avenue'
        booking.pickup_location.save()
        page = self.client.get(tokens.links(booking)['receipt_page_url'])
        office = page.content.decode().split('class="pr-biz"')[1].split('</p>')[0]   # the receipt's own address block
        self.assertIn('Kenyatta Avenue, Nairobi', office)
        self.assertNotIn('Moi Avenue', office)

    @override_settings(ADMIN_NOTIFY_EMAILS=['owner@example.com'], SITE_URL='https://www.zidicarhire.com')
    def test_confirmation_email_has_pdf_and_signed_link(self):
        booking = paid_booking()
        notify_booking_paid(booking)
        customer = next(m for m in mail.outbox if m.to == ['a@example.com'])
        name, content, mimetype = customer.attachments[0]
        self.assertEqual(mimetype, 'application/pdf')
        self.assertTrue(content.startswith(b'%PDF'))
        self.assertIn(f'https://www.zidicarhire.com/bookings/{booking.ref}/receipt.pdf?t={booking_token(booking.ref)}',
                      customer.body)


class FindBookingTests(TestCase):
    def setUp(self):
        self.booking = paid_booking()

    def find(self, ref, phone):
        return self.client.post('/bookings/find/', {'ref': ref, 'phone': phone})

    def test_number_and_phone_open_the_booking(self):
        res = self.find(self.booking.ref.lower(), '0712 345 678')
        self.assertEqual(res.status_code, 302)
        self.assertIn(f'?t={booking_token(self.booking.ref)}', res.url)
        self.assertEqual(self.client.get(f'/bookings/{self.booking.ref}/receipt.pdf').status_code, 200)

    def test_wrong_phone_is_refused_without_saying_which_part_is_wrong(self):
        res = self.find(self.booking.ref, '0799999999')
        self.assertContains(res, 'find a booking with that number and phone')
        self.assertEqual(self.client.get(f'/bookings/{self.booking.ref}/receipt.pdf').status_code, 403)

    def test_lookups_are_rate_limited(self):
        with mock.patch('bookings.views.rate_limited', return_value=True):
            res = self.find(self.booking.ref, '0712345678')
        self.assertContains(res, 'Too many tries')
