"""PayHero integration. Every HTTP call to PayHero is mocked."""
import base64
import json
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from bookings.models import Booking
from bookings.services import check_pending_payment, start_payment
from fleet.test_utils import make_car, make_location, trip

from . import payhero
from .models import Payment

LIVE = dict(FAKE_PAYMENTS=False, PAYHERO_AUTH_TOKEN='Basic c2VjcmV0OnRva2Vu', PAYHERO_API_USERNAME='',
            PAYHERO_API_PASSWORD='', PAYHERO_CHANNEL_ID='1234', SITE_URL='https://www.zidicarhire.com',
            ADMIN_NOTIFY_EMAILS=['owner@example.com'])


def fake_response(status=200, data=None):
    response = mock.Mock(status_code=status)
    response.json.return_value = data if data is not None else {}
    return response


def make_booking(car, **kwargs):
    start, end = trip()
    defaults = dict(car=car, customer_name='Wanjiku', phone='254712345678', email='w@example.com',
                    pickup_location=car.location, return_location=car.location, pickup_date=start,
                    return_date=end, days=3, daily_rate=4000, amount=12000, status=Booking.Status.PENDING,
                    payment_requested_at=timezone.now())
    defaults.update(kwargs)
    return Booking.objects.create(**defaults)


class AuthAndConfigTests(TestCase):
    @override_settings(PAYHERO_AUTH_TOKEN='abc123', PAYHERO_API_USERNAME='', PAYHERO_API_PASSWORD='')
    def test_token_gets_basic_prefix(self):
        self.assertEqual(payhero.auth_header(), 'Basic abc123')

    @override_settings(PAYHERO_AUTH_TOKEN='Basic abc123')
    def test_token_used_as_is(self):
        self.assertEqual(payhero.auth_header(), 'Basic abc123')

    @override_settings(PAYHERO_AUTH_TOKEN='', PAYHERO_API_USERNAME='user', PAYHERO_API_PASSWORD='pass')
    def test_token_built_from_username_and_password(self):
        self.assertEqual(payhero.auth_header(), 'Basic ' + base64.b64encode(b'user:pass').decode())

    @override_settings(FAKE_PAYMENTS=False, PAYHERO_AUTH_TOKEN='', PAYHERO_API_USERNAME='', PAYHERO_API_PASSWORD='',
                       PAYHERO_CHANNEL_ID='', SITE_URL='https://www.zidicarhire.com')
    def test_missing_settings_are_reported(self):
        problems = payhero.config_problems()
        self.assertEqual(len(problems), 2)
        self.assertIn('PayHero login is missing', problems[0])

    @override_settings(FAKE_PAYMENTS=True, PAYHERO_AUTH_TOKEN='')
    def test_fake_mode_needs_nothing(self):
        self.assertEqual(payhero.config_problems(), [])


@override_settings(**LIVE)
class StkPushTests(TestCase):
    def setUp(self):
        self.car = make_car(make_location('nairobi'))

    @mock.patch('payments.payhero.requests.post')
    def test_push_payload_and_attempt_recorded_without_logging_the_token(self, post):
        post.return_value = fake_response(201, {'success': True, 'status': 'QUEUED', 'reference': 'PH1',
                                                'CheckoutRequestID': 'ws_CO_1'})
        booking = make_booking(self.car)
        with self.assertLogs('payments.payhero', level='INFO') as logs:
            start_payment(booking)
        payload = post.call_args.kwargs['json']
        self.assertEqual(payload['amount'], 12000)
        self.assertEqual(payload['channel_id'], 1234)
        self.assertEqual(payload['external_reference'], booking.ref)
        self.assertEqual(payload['callback_url'], 'https://www.zidicarhire.com/payments/callback/')
        self.assertEqual(post.call_args.kwargs['headers']['Authorization'], 'Basic c2VjcmV0OnRva2Vu')
        self.assertNotIn('c2VjcmV0OnRva2Vu', '\n'.join(logs.output))
        attempt = booking.payments.get()
        self.assertEqual((attempt.checkout_request_id, attempt.payhero_reference, attempt.status),
                         ('ws_CO_1', 'PH1', Payment.Status.PENDING))
        booking.refresh_from_db()
        self.assertEqual(booking.checkout_request_id, 'ws_CO_1')

    @mock.patch('payments.payhero.requests.post')
    def test_refused_push_is_recorded_as_failed(self, post):
        post.return_value = fake_response(400, {'success': False, 'error_message': 'Invalid phone'})
        booking = make_booking(self.car)
        with self.assertRaises(payhero.PayHeroError):
            start_payment(booking)
        attempt = booking.payments.get()
        self.assertEqual(attempt.status, Payment.Status.FAILED)
        self.assertIn('Invalid phone', attempt.result_desc)


@override_settings(**LIVE)
class CallbackTests(TestCase):
    def setUp(self):
        self.car = make_car(make_location('nairobi'))
        self.booking = make_booking(self.car, checkout_request_id='ws_CO_1', payhero_reference='PH1')
        self.attempt = Payment.objects.create(booking=self.booking, reference=self.booking.ref, amount=12000,
                                              phone='254712345678', checkout_request_id='ws_CO_1',
                                              payhero_reference='PH1')

    def callback(self, **overrides):
        result = {'ExternalReference': self.booking.ref, 'CheckoutRequestID': 'ws_CO_1', 'ResultCode': 0,
                  'ResultDesc': 'The service request is processed successfully.', 'MpesaReceiptNumber': 'SJK1ABC2DE',
                  'Amount': 12000, 'Status': 'Success'}
        result.update(overrides)
        return self.client.post('/payments/callback/', json.dumps({'status': True, 'response': result}),
                                content_type='application/json')

    @mock.patch('payments.payhero.transaction_status', return_value={'status': 'SUCCESS'})
    def test_success_marks_paid_once_and_emails_once(self, _status):
        self.assertEqual(self.callback().json(), {'ok': True})
        self.booking.refresh_from_db()
        self.assertEqual((self.booking.status, self.booking.mpesa_receipt, self.booking.amount_paid),
                         (Booking.Status.PAID, 'SJK1ABC2DE', 12000))
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, Payment.Status.SUCCESS)
        self.assertEqual(self.attempt.raw_callback['response']['MpesaReceiptNumber'], 'SJK1ABC2DE')
        sent = len(mail.outbox)
        self.callback()  # duplicate callback
        self.assertEqual(len(mail.outbox), sent)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.PAID)

    def test_cancelled_by_customer(self):
        self.callback(ResultCode=1032, ResultDesc='Request cancelled by user', Status='Failed')
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.FAILED)
        self.assertIn('You cancelled the M-Pesa prompt', self.booking.result_desc)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, Payment.Status.CANCELLED)

    def test_insufficient_funds(self):
        self.callback(ResultCode=1, ResultDesc='Insufficient balance', Status='Failed')
        self.booking.refresh_from_db()
        self.assertIn('balance was too low', self.booking.result_desc)

    def test_wrong_checkout_request_id_is_ignored(self):
        res = self.callback(CheckoutRequestID='ws_CO_OLD')
        self.assertEqual(res.json()['error'], 'stale request')
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.PENDING)

    def test_underpayment_is_not_accepted(self):
        self.callback(Amount=100)
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.FAILED)
        self.assertIn('KES 100', self.booking.result_desc)

    def test_unknown_reference(self):
        res = self.callback(ExternalReference='ZCHNOPE', CheckoutRequestID='ws_CO_X')
        self.assertEqual(res.json(), {'ok': False, 'error': 'unknown reference'})

    @mock.patch('payments.payhero.transaction_status', return_value={'status': 'FAILED'})
    def test_forged_success_is_rejected_by_status_check(self, _status):
        res = self.callback()
        self.assertEqual(res.json()['error'], 'not verified')
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.PENDING)

    @mock.patch('payments.payhero.transaction_status', return_value={'status': 'SUCCESS'})
    def test_late_payment_after_failure_is_still_accepted(self, _status):
        Booking.objects.filter(pk=self.booking.pk).update(status=Booking.Status.FAILED)
        self.callback()
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, Booking.Status.PAID)

    def test_invalid_json(self):
        res = self.client.post('/payments/callback/', 'not json', content_type='application/json')
        self.assertEqual(res.json()['ok'], False)


@override_settings(**LIVE)
class StatusCheckFallbackTests(TestCase):
    def setUp(self):
        cache.clear()
        self.car = make_car(make_location('nairobi'))

    def pending(self, seconds_ago):
        booking = make_booking(self.car, payhero_reference='PH9',
                               payment_requested_at=timezone.now() - timedelta(seconds=seconds_ago))
        Payment.objects.create(booking=booking, reference=booking.ref, amount=12000, phone=booking.phone,
                               payhero_reference='PH9')
        return booking

    @mock.patch('payments.payhero.transaction_status')
    def test_not_asked_too_early(self, status):
        check_pending_payment(self.pending(5))
        status.assert_not_called()

    @mock.patch('payments.payhero.transaction_status', return_value={'status': 'SUCCESS', 'provider_reference': 'SJK9'})
    def test_success_without_callback(self, _status):
        booking = check_pending_payment(self.pending(30))
        self.assertEqual((booking.status, booking.mpesa_receipt), (Booking.Status.PAID, 'SJK9'))
        self.assertEqual(booking.payments.get().status, Payment.Status.SUCCESS)

    @mock.patch('payments.payhero.transaction_status', return_value={'status': 'FAILED'})
    def test_failure_without_callback(self, _status):
        self.assertEqual(check_pending_payment(self.pending(30)).status, Booking.Status.FAILED)

    @mock.patch('payments.payhero.transaction_status', return_value={'status': 'QUEUED'})
    def test_gives_up_after_three_minutes(self, _status):
        booking = check_pending_payment(self.pending(200))
        self.assertEqual(booking.status, Booking.Status.FAILED)
        self.assertIn("wasn't answered in time", booking.result_desc)

    @mock.patch('payments.payhero.transaction_status', side_effect=ValueError('PayHero down'))
    def test_payhero_errors_dont_break_polling(self, _status):
        self.assertEqual(check_pending_payment(self.pending(30)).status, Booking.Status.PENDING)

    @mock.patch('payments.payhero.transaction_status', return_value={'status': 'QUEUED'})
    def test_status_endpoint_uses_fallback(self, status):
        booking = self.pending(30)
        res = self.client.get(f'/bookings/{booking.ref}/status/')
        self.assertEqual(res.json()['booking']['status'], 'pending')
        status.assert_called_once_with('PH9')


@override_settings(**LIVE)
class RetryTests(TestCase):
    def setUp(self):
        self.car = make_car(make_location('nairobi'))

    def retry(self, booking):
        with mock.patch('bookings.views.rate_limited', return_value=False):
            return self.client.post(f'/bookings/{booking.ref}/retry/', '{}', content_type='application/json')

    @mock.patch('payments.payhero.requests.post')
    def test_retry_sends_a_new_prompt_and_records_a_new_attempt(self, post):
        post.return_value = fake_response(201, {'success': True, 'reference': 'PH2', 'CheckoutRequestID': 'ws_CO_2'})
        booking = make_booking(self.car, status=Booking.Status.FAILED, checkout_request_id='ws_CO_1')
        Payment.objects.create(booking=booking, reference=booking.ref, amount=12000, phone=booking.phone,
                               checkout_request_id='ws_CO_1', status=Payment.Status.FAILED)
        res = self.retry(booking)
        self.assertEqual(res.json()['booking']['status'], 'pending')
        booking.refresh_from_db()
        self.assertEqual(booking.checkout_request_id, 'ws_CO_2')
        self.assertEqual(booking.payments.count(), 2)

    def test_retry_refused_when_car_was_taken(self):
        booking = make_booking(self.car, status=Booking.Status.FAILED)
        make_booking(self.car, status=Booking.Status.PAID)
        self.assertEqual(self.retry(booking).status_code, 409)

    def test_retry_on_paid_booking_changes_nothing(self):
        booking = make_booking(self.car, status=Booking.Status.PAID)
        self.assertEqual(self.retry(booking).json()['booking']['status'], 'paid')


class SettingsCheckPageTests(TestCase):
    def setUp(self):
        cache.clear()
        self.staff = get_user_model().objects.create_user('staff', password='pw', is_staff=True)

    def test_non_staff_are_sent_to_login(self):
        res = self.client.get('/dashboard/settings-check/')
        self.assertEqual(res.status_code, 302)
        self.assertIn('/dashboard/login/', res.url)

    @override_settings(PAYHERO_AUTH_TOKEN='Basic sup3rs3cret', EMAIL_HOST_PASSWORD='mailpass123')
    def test_shows_status_but_never_secrets(self):
        self.client.force_login(self.staff)
        res = self.client.get('/dashboard/settings-check/')
        self.assertContains(res, 'Filled (Basic Auth token)')
        self.assertNotContains(res, 'sup3rs3cret')
        self.assertNotContains(res, 'mailpass123')

    @override_settings(FAKE_PAYMENTS=True)
    def test_test_push_in_fake_mode_and_rate_limit(self):
        self.client.force_login(self.staff)
        for _ in range(4):
            self.client.post('/dashboard/settings-check/', {'phone': '0712345678'})
        tests = Payment.objects.filter(is_test=True)
        self.assertEqual(tests.count(), 3)
        self.assertTrue(all(t.amount == 1 and t.status == Payment.Status.SUCCESS for t in tests))

    @override_settings(FAKE_PAYMENTS=False, PAYHERO_AUTH_TOKEN='', PAYHERO_API_USERNAME='', PAYHERO_API_PASSWORD='')
    def test_dashboard_banner_when_payhero_missing(self):
        self.client.force_login(self.staff)
        self.assertContains(self.client.get('/dashboard/'), "M-Pesa payments are not set up")

    @override_settings(FAKE_PAYMENTS=False, PAYHERO_AUTH_TOKEN='Basic x', PAYHERO_CHANNEL_ID='1')
    @mock.patch('payments.payhero.requests.post')
    def test_test_push_callback_updates_the_test_payment(self, post):
        post.return_value = fake_response(201, {'success': True, 'reference': 'PHT', 'CheckoutRequestID': 'ws_T'})
        self.client.force_login(self.staff)
        self.client.post('/dashboard/settings-check/', {'phone': '0712345678'})
        test = Payment.objects.get(is_test=True)
        self.assertEqual(post.call_args.kwargs['json']['amount'], 1)
        self.client.post('/payments/callback/', json.dumps({'response': {
            'ExternalReference': test.reference, 'CheckoutRequestID': 'ws_T', 'ResultCode': 0,
            'Status': 'Success', 'MpesaReceiptNumber': 'SJT1', 'Amount': 1}}), content_type='application/json')
        test.refresh_from_db()
        self.assertEqual((test.status, test.mpesa_receipt), (Payment.Status.SUCCESS, 'SJT1'))
