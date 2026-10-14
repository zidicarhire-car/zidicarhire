"""PayHero Kenya client. Docs: https://docs.payhero.co.ke"""
import base64
import logging
import secrets

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

BASE_URL = 'https://backend.payhero.co.ke/api/v2'

# M-Pesa result codes PayHero passes through, in words a customer understands.
RESULT_MESSAGES = {
    '1': 'Your M-Pesa balance was too low for this payment. Top up, then send a new prompt.',
    '1001': 'Another M-Pesa payment was in progress on your phone. Wait a minute, then send a new prompt.',
    '1019': 'The M-Pesa prompt expired before it was answered. Send a new prompt to try again.',
    '1025': "M-Pesa couldn't send the prompt to your phone. Check the number and send a new prompt.",
    '1032': 'You cancelled the M-Pesa prompt. Send a new prompt when you are ready to pay.',
    '1037': "Your phone didn't answer the M-Pesa prompt in time. Make sure it is on and unlocked, then send a new prompt.",
    '2001': 'The M-Pesa PIN was wrong. Send a new prompt and enter your PIN again.',
    '9999': "M-Pesa couldn't send the prompt to your phone. Send a new prompt to try again.",
}
CANCELLED_CODES = {'1032'}


class PayHeroError(Exception):
    pass


def friendly_result(code, desc=''):
    return RESULT_MESSAGES.get(str(code).strip(), desc or 'The M-Pesa payment was not completed. Send a new prompt to try again.')


def auth_header():
    """'Basic ...' from PAYHERO_AUTH_TOKEN, or built from PAYHERO_API_USERNAME and PAYHERO_API_PASSWORD."""
    token = (settings.PAYHERO_AUTH_TOKEN or '').strip()
    if token:
        return token if token.lower().startswith('basic ') else f'Basic {token}'
    user, password = settings.PAYHERO_API_USERNAME, settings.PAYHERO_API_PASSWORD
    if user and password:
        return 'Basic ' + base64.b64encode(f'{user}:{password}'.encode()).decode()
    return ''


def config_problems():
    """What's missing for real M-Pesa payments. Empty when everything needed is set (or in test mode)."""
    if settings.FAKE_PAYMENTS:
        return []
    problems = []
    if not auth_header():
        problems.append('PayHero login is missing: fill PAYHERO_AUTH_TOKEN, or PAYHERO_API_USERNAME and '
                        'PAYHERO_API_PASSWORD, in .env.')
    channel = settings.PAYHERO_CHANNEL_ID
    if not channel:
        problems.append('PAYHERO_CHANNEL_ID is missing in .env.')
    elif not str(channel).isdigit():
        problems.append('PAYHERO_CHANNEL_ID must be a number (PayHero > Payment Channels).')
    if not settings.SITE_URL.startswith('https://'):
        problems.append(f'SITE_URL is {settings.SITE_URL}. PayHero can only send payment results to a public '
                        'https:// address, so payments will only confirm through the slower status check.')
    return problems


def _headers():
    header = auth_header()
    if not header:
        raise PayHeroError('PayHero login is not set in .env')
    return {'Authorization': header, 'Content-Type': 'application/json'}


def _mask(phone):
    phone = str(phone)
    return f'{phone[:6]}***{phone[-3:]}' if len(phone) > 9 else phone


def stk_push(amount, phone, reference, customer_name, callback_url):
    """Sends the M-Pesa prompt. Returns {'success', 'status', 'reference', 'CheckoutRequestID'}."""
    logger.info('STK push %s: KES %s to %s', reference, amount, _mask(phone))
    if settings.FAKE_PAYMENTS:
        data = {
            'success': True,
            'status': 'QUEUED',
            'reference': 'FAKE' + secrets.token_hex(4).upper(),
            'CheckoutRequestID': 'ws_CO_FAKE_' + secrets.token_hex(6),
        }
        logger.info('STK push %s: simulated (FAKE_PAYMENTS), CheckoutRequestID %s', reference, data['CheckoutRequestID'])
        return data

    try:
        channel_id = int(settings.PAYHERO_CHANNEL_ID)
    except (TypeError, ValueError):
        logger.error('STK push %s refused: PAYHERO_CHANNEL_ID is missing or not a number', reference)
        raise PayHeroError('PAYHERO_CHANNEL_ID is missing or not a number')

    payload = {
        'amount': int(amount),
        'phone_number': phone,
        'channel_id': channel_id,
        'provider': 'm-pesa',
        'external_reference': reference,
        'customer_name': customer_name,
        'callback_url': callback_url,
    }
    try:
        response = requests.post(f'{BASE_URL}/payments', json=payload, headers=_headers(), timeout=20)
    except requests.RequestException as exc:
        logger.warning('STK push %s: could not reach PayHero (%s)', reference, exc.__class__.__name__)
        raise PayHeroError(f'Could not reach PayHero: {exc.__class__.__name__}') from exc

    try:
        data = response.json()
    except ValueError:
        data = {}

    if response.status_code >= 400 or data.get('success') is False:
        message = data.get('error_message') or data.get('message') or f'PayHero returned HTTP {response.status_code}'
        logger.warning('STK push %s refused by PayHero: HTTP %s, %s', reference, response.status_code, message)
        raise PayHeroError(message)
    logger.info('STK push %s accepted: status %s, CheckoutRequestID %s', reference, data.get('status'),
                data.get('CheckoutRequestID'))
    return data


def transaction_status(reference):
    """Looks up a payment using the 'reference' PayHero returned from stk_push."""
    if settings.FAKE_PAYMENTS:
        return {'status': 'SUCCESS'}
    response = requests.get(
        f'{BASE_URL}/transaction-status', params={'reference': reference}, headers=_headers(), timeout=15
    )
    data = response.json()
    logger.info('Status check %s: %s', reference, data.get('status'))
    return data
