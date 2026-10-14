import json
import logging

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from bookings.models import Booking
from bookings.services import mark_failed, mark_paid, record_result

from . import payhero
from .models import Payment

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def payhero_callback(request):
    """
    PayHero posts the payment result here. Payload shape:
    {"status": true, "response": {"ExternalReference", "CheckoutRequestID", "ResultCode",
     "ResultDesc", "MpesaReceiptNumber", "Amount", "Status", ...}}
    Always answers 200 so PayHero doesn't keep retrying.
    """
    try:
        payload = json.loads(request.body or b'{}')
    except ValueError:
        logger.warning('PayHero callback with invalid JSON')
        return JsonResponse({'ok': False, 'error': 'invalid json'})
    if not isinstance(payload, dict):
        return JsonResponse({'ok': False, 'error': 'invalid json'})

    result = payload.get('response') if isinstance(payload.get('response'), dict) else payload
    ref = str(result.get('ExternalReference') or result.get('external_reference') or '')
    checkout_id = str(result.get('CheckoutRequestID') or '')
    code = str(result.get('ResultCode', '')).strip()
    description = str(result.get('ResultDesc') or '')
    receipt = str(result.get('MpesaReceiptNumber') or '')
    success = code == '0' and str(result.get('Status', 'Success')).lower() == 'success'
    logger.info('PayHero callback for %s: ResultCode %s (%s)', ref or 'no reference', code or '-', description or '-')

    attempt = Payment.objects.filter(checkout_request_id=checkout_id).first() if checkout_id else None
    if attempt is not None:
        status = Payment.Status.SUCCESS if success else (
            Payment.Status.CANCELLED if code in payhero.CANCELLED_CODES else Payment.Status.FAILED)
        record_result(attempt, status, code, description, receipt, raw=payload)

    if attempt is not None and attempt.is_test:
        return JsonResponse({'ok': True})

    booking = Booking.objects.filter(ref=ref).first() if ref else None
    if not booking:
        logger.warning('PayHero callback for unknown booking: %s', ref)
        return JsonResponse({'ok': False, 'error': 'unknown reference'})

    if booking.status in Booking.PAID_STATES:
        logger.info('PayHero callback for %s ignored: already paid', booking.ref)
        return JsonResponse({'ok': True})

    if booking.checkout_request_id and checkout_id and checkout_id != booking.checkout_request_id:
        logger.warning('CheckoutRequestID mismatch for %s (an older prompt); booking left unchanged', booking.ref)
        return JsonResponse({'ok': False, 'error': 'stale request'})

    if success:
        amount = result.get('Amount')
        try:
            if amount is not None and float(amount) < booking.due_now:
                logger.warning('Underpayment on %s: got %s, expected %s', booking.ref, amount, booking.due_now)
                mark_failed(booking.pk, f'We received KES {amount} but expected KES {booking.due_now:,}. '
                                        'Chat with us and we will sort it out.')
                return JsonResponse({'ok': True})
        except (TypeError, ValueError):
            pass

        # Double-check with PayHero so a forged callback can't confirm a booking.
        if not settings.FAKE_PAYMENTS and booking.payhero_reference:
            try:
                verified = str(payhero.transaction_status(booking.payhero_reference).get('status', '')).upper()
                if verified in ('FAILED', 'CANCELLED'):
                    logger.warning('Callback said success but PayHero says %s for %s', verified, booking.ref)
                    return JsonResponse({'ok': False, 'error': 'not verified'})
            except Exception:
                logger.exception('Could not verify %s with PayHero; trusting matched callback', booking.ref)

        try:
            paid = int(float(amount)) if amount is not None else None
        except (TypeError, ValueError):
            paid = None
        mark_paid(booking.pk, receipt=receipt, desc=description, amount_paid=paid)
    else:
        mark_failed(booking.pk, payhero.friendly_result(code, description))

    return JsonResponse({'ok': True})
