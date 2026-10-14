"""Checks the customer's details. Each problem names the field and says how to fix it."""
import re

from django.core.exceptions import ValidationError
from django.core.validators import validate_email

from .pricing import QuoteError
from .utils import normalize_phone

ID_RE = re.compile(r'^[A-Z0-9]{6,12}$')
LICENCE_RE = re.compile(r'^[A-Z0-9][A-Z0-9/-]{3,19}$')


def clean_customer(data):
    """Returns a dict of cleaned values, or raises QuoteError(message, field)."""
    name = ' '.join(str(data.get('name') or '').split())[:120]
    if len(name) < 2:
        raise QuoteError('Enter your full name as it appears on your ID.', field='name')

    phone = normalize_phone(data.get('phone'))
    if not phone:
        raise QuoteError('Enter the Safaricom number that will pay, like 0712 345 678 or 0110 123 456.',
                         field='phone')

    email = str(data.get('email') or '').strip()[:254]
    if email:
        try:
            validate_email(email)
        except ValidationError:
            raise QuoteError('That email address looks incomplete. Check it, or leave it blank.', field='email')

    id_number = re.sub(r'[\s-]', '', str(data.get('id_number') or '')).upper()
    if not ID_RE.match(id_number):
        raise QuoteError('Enter your national ID number (7 or 8 digits) or your passport number.',
                         field='id_number')

    licence = re.sub(r'\s', '', str(data.get('licence_number') or '')).upper()
    if not LICENCE_RE.match(licence):
        raise QuoteError("Enter the number on your driving licence (letters, numbers and dashes).",
                         field='licence_number')

    return {
        'customer_name': name, 'phone': phone, 'email': email, 'id_number': id_number,
        'licence_number': licence, 'notes': str(data.get('notes') or '').strip()[:500],
    }
