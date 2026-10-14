"""Dashboard page that shows whether PayHero and email are set up, and sends a KES 1 test prompt."""
import logging
import secrets

from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.shortcuts import redirect, render

from bookings.services import callback_url, record_result
from bookings.utils import normalize_phone
from payments import payhero
from payments.models import Payment

from .views import _ctx, staff_page

logger = logging.getLogger(__name__)

TEST_PUSH_LIMIT = 3       # prompts per staff member...
TEST_PUSH_WINDOW = 600    # ...per 10 minutes
DEV_KEY = 'dev-only-insecure-key-change-me'


def setting_rows():
    """(group, label, ok, detail). Shows whether secrets are filled, never their values."""
    s = settings
    if s.PAYHERO_AUTH_TOKEN:
        login = 'Filled (Basic Auth token)'
    elif s.PAYHERO_API_USERNAME and s.PAYHERO_API_PASSWORD:
        login = 'Filled (API username and password)'
    else:
        login = 'Missing: fill PAYHERO_AUTH_TOKEN, or PAYHERO_API_USERNAME and PAYHERO_API_PASSWORD'
    channel_ok = bool(s.PAYHERO_CHANNEL_ID) and str(s.PAYHERO_CHANNEL_ID).isdigit()
    url = callback_url()
    https = url.startswith('https://')
    emails_on = bool(s.EMAIL_HOST and s.EMAIL_HOST_USER and s.EMAIL_HOST_PASSWORD)
    biz = s.BUSINESS
    return [
        ('M-Pesa (PayHero)', 'Payment mode', not s.FAKE_PAYMENTS,
         'Test mode (FAKE_PAYMENTS=true): no real prompts, bookings pay themselves after a few seconds.'
         if s.FAKE_PAYMENTS else 'Live: customers get real M-Pesa prompts.'),
        ('M-Pesa (PayHero)', 'PayHero login', bool(payhero.auth_header()), login),
        ('M-Pesa (PayHero)', 'Channel ID (PAYHERO_CHANNEL_ID)', channel_ok,
         'Filled' if channel_ok else 'Missing: the number from PayHero > Payment Channels'),
        ('M-Pesa (PayHero)', 'Till number (MPESA_TILL_NUMBER)', bool(s.MPESA_TILL_NUMBER),
         s.MPESA_TILL_NUMBER or 'Missing (it is printed on receipts)'),
        ('M-Pesa (PayHero)', 'Name customers see (MPESA_ACCOUNT_NAME)', bool(s.MPESA_ACCOUNT_NAME),
         s.MPESA_ACCOUNT_NAME or 'Missing'),
        ('M-Pesa (PayHero)', 'Callback URL', https,
         url if https else f'{url} (PayHero needs a public https address. Payments still confirm through the '
                           'status check, just more slowly.)'),
        ('Email', 'Mail server (EMAIL_HOST, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD)', emails_on,
         f'Filled: emails go out through {s.EMAIL_HOST}' if emails_on
         else 'Not filled: emails are printed in the server log instead of being sent'),
        ('Email', 'From address (DEFAULT_FROM_EMAIL)', bool(s.DEFAULT_FROM_EMAIL), s.DEFAULT_FROM_EMAIL or 'Missing'),
        ('Email', 'Booking alerts go to (ADMIN_NOTIFY_EMAILS)', bool(s.ADMIN_NOTIFY_EMAILS),
         ', '.join(s.ADMIN_NOTIFY_EMAILS) or 'Missing: nobody gets booking alerts by email'),
        ('Site', 'Secret key (SECRET_KEY)', s.SECRET_KEY != DEV_KEY,
         'Filled' if s.SECRET_KEY != DEV_KEY else 'Using the development key. Set your own before going live.'),
        ('Site', 'Debug mode (DEBUG)', not s.DEBUG,
         'On. Fine on your computer; turn it off on the live site.' if s.DEBUG else 'Off'),
        ('Site', 'Site address (SITE_URL)', https, s.SITE_URL),
        ('Business details', 'Phone (BUSINESS_PHONE)', bool(biz['phone']), biz['phone'] or 'Missing'),
        ('Business details', 'WhatsApp (BUSINESS_WHATSAPP)', bool(biz['whatsapp']), biz['whatsapp'] or 'Missing'),
        ('Business details', 'Address (BUSINESS_ADDRESS)', bool(biz['address']), biz['address'] or 'Missing'),
        ('Business details', 'KRA PIN (KRA_PIN, optional)', True, biz['kra_pin'] or 'Not set, so left off receipts'),
    ]


def _send_test_push(request):
    phone = normalize_phone(request.POST.get('phone'))
    if not phone:
        messages.error(request, 'Enter a Safaricom number like 0712 345 678.')
        return
    key = f'testpush:{request.user.pk}'
    cache.add(key, 0, TEST_PUSH_WINDOW)
    if cache.incr(key) > TEST_PUSH_LIMIT:
        messages.error(request, 'You have sent 3 test prompts in the last 10 minutes. Wait a few minutes, then try again.')
        return
    attempt = Payment.objects.create(is_test=True, requested_by=request.user, amount=1, phone=phone,
                                     reference='TEST' + secrets.token_hex(4).upper())
    try:
        data = payhero.stk_push(amount=1, phone=phone, reference=attempt.reference,
                                customer_name=request.user.get_full_name() or request.user.get_username(),
                                callback_url=callback_url())
    except payhero.PayHeroError as exc:
        record_result(attempt, Payment.Status.FAILED, desc=f'Prompt not sent: {exc}')
        messages.error(request, f'PayHero did not send the prompt: {exc}')
        return
    attempt.checkout_request_id = data.get('CheckoutRequestID', '') or ''
    attempt.payhero_reference = data.get('reference', '') or ''
    attempt.save(update_fields=['checkout_request_id', 'payhero_reference', 'updated_at'])
    if settings.FAKE_PAYMENTS:
        record_result(attempt, Payment.Status.SUCCESS, '0', 'Simulated: FAKE_PAYMENTS is on, so no real prompt was sent')
        messages.info(request, 'Test mode is on, so no real prompt was sent. Set FAKE_PAYMENTS=false in .env to test M-Pesa.')
    else:
        messages.success(request, f'Prompt for KES 1 sent to {attempt.masked_phone}. Approve it on the phone, '
                                  'then click "Check result".')


def _check_test_push(request):
    attempt = Payment.objects.filter(pk=request.POST.get('payment') or 0, is_test=True).first()
    if attempt is None or not attempt.payhero_reference:
        messages.error(request, 'That test prompt has no PayHero reference to check.')
        return
    try:
        data = payhero.transaction_status(attempt.payhero_reference)
    except Exception as exc:  # noqa: BLE001
        logger.warning('Test status check failed: %s', exc.__class__.__name__)
        messages.error(request, "Couldn't reach PayHero to check the result. Try again in a minute.")
        return
    status = str(data.get('status', '')).upper()
    mapping = {'SUCCESS': Payment.Status.SUCCESS, 'FAILED': Payment.Status.FAILED,
               'CANCELLED': Payment.Status.CANCELLED}
    if status in mapping:
        record_result(attempt, mapping[status], desc=f'Status check: {status}',
                      receipt=data.get('provider_reference') or '')
    messages.info(request, f'PayHero says: {status or "no result yet"}.')


@staff_page
def settings_check(request):
    if request.method == 'POST':
        if request.POST.get('action') == 'check':
            _check_test_push(request)
        else:
            _send_test_push(request)
        return redirect('dashboard:settings_check')
    groups = {}
    for group, label, ok, detail in setting_rows():
        groups.setdefault(group, []).append({'label': label, 'ok': ok, 'detail': detail})
    return render(request, 'dashboard/settings_check.html', _ctx(
        request, nav='settings', groups=groups,
        tests=Payment.objects.filter(is_test=True).select_related('requested_by')[:10],
    ))
