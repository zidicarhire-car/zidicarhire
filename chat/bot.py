"""
The chat's automatic assistant. It answers common questions straight away from the site's own data
(cars, prices, branches, hours, payment rules), and hands the chat to a person when asked, when the
question is about changing or cancelling a booking, or when it can't help twice in a row.

It only speaks until a team member replies; after that the conversation is between people.
"""
import re

from django.conf import settings
from django.contrib.humanize.templatetags.humanize import intcomma
from django.urls import reverse
from django.utils import timezone

from fleet.models import Car, Location

from .models import Message
from .services import agent_online

TALK_TO_PERSON = 'Talk to a person'
FALLBACK_LIMIT = 2      # unanswered questions in a row before a person is called in

# (topic, keywords). Phrases are matched as text, single words as whole words. Swahili basics included.
TOPICS = [
    ('agent', ['talk to a person', 'talk to someone', 'speak to', 'real person', 'human', 'agent', 'person',
               'customer care', 'representative', 'operator', 'call me', 'call back', 'mtu', 'nipigie']),
    ('changes', ['cancel', 'cancellation', 'refund', 'change my booking', 'change the date', 'change dates',
                 'reschedule', 'extend', 'extension', 'complain', 'complaint', 'problem', 'accident', 'breakdown']),
    ('mybooking', ['my booking', 'booking number', 'reference', 'receipt', 'confirmation', 'find booking',
                   'booking status']),
    ('payment', ['pay', 'paying', 'payment', 'mpesa', 'm-pesa', 'deposit', 'booking fee', 'till', 'lipa', 'kulipa',
                 'balance', 'prompt', 'stk', 'cash', 'card']),
    ('prices', ['price', 'prices', 'cost', 'costs', 'rate', 'rates', 'how much', 'cheap', 'cheapest', 'bei',
                'charges', 'charge', 'per day', 'daily', 'weekly', 'monthly', 'pesa ngapi', 'ngapi']),
    ('documents', ['document', 'documents', 'id', 'passport', 'licence', 'license', 'requirements', 'require',
                   'required', 'need to bring', 'age', 'kitambulisho']),
    ('locations', ['where', 'location', 'locations', 'branch', 'branches', 'city', 'cities', 'office', 'airport',
                   'delivery', 'deliver', 'pick up', 'pickup', 'pick-up', 'collect', 'hotel', 'one way', 'one-way']),
    ('hours', ['hours', 'open', 'opening', 'close', 'closing', 'what time', 'saa ngapi', 'weekend', 'sunday',
               'holiday']),
    ('booking', ['book', 'booking', 'reserve', 'reservation', 'hire', 'rent', 'rental', 'available',
                 'availability', 'kodi', 'kukodisha']),
    ('contact', ['phone', 'call', 'number', 'whatsapp', 'email', 'contact']),
    ('greeting', ['hi', 'hello', 'hey', 'habari', 'mambo', 'niaje', 'sasa', 'jambo', 'good morning',
                  'good afternoon', 'good evening', 'hallo']),
    ('thanks', ['thanks', 'thank you', 'asante', 'sawa', 'ok thanks', 'okay']),
]
REF_RE = re.compile(r'\bZCH[0-9A-F]{6,10}\b', re.I)


def kes(amount):
    return f'KES {intcomma(amount)}'


def _url(name):
    return settings.SITE_URL + reverse(name)


def _hours():
    return f'{settings.BUSINESS_OPEN_TIME:%H:%M} to {settings.BUSINESS_CLOSE_TIME:%H:%M}'


def _contact_line():
    phone = settings.BUSINESS.get('phone') or ''
    wa = settings.BUSINESS.get('whatsapp') or ''
    parts = [f'call {phone}'] if phone else []
    if wa:
        parts.append(f'WhatsApp https://wa.me/{wa}')
    return ' or '.join(parts)


def _words(text):
    return set(re.findall(r"[a-z0-9'-]+", text))


def match_topic(text):
    """The best topic for a message, or None. Ties go to the topic listed first in TOPICS."""
    lowered = ' ' + text.lower() + ' '
    words = _words(lowered)
    topics = list(TOPICS)
    cities = [name.lower() for name in Location.objects.active().values_list('name', flat=True)]
    best, best_hits = None, 0
    for topic, keywords in topics:
        keys = keywords + (cities if topic == 'locations' else [])
        hits = sum(1 for k in keys if (k in lowered if ' ' in k or '-' in k else k in words))
        if topic == 'mybooking' and REF_RE.search(text):
            hits += 2
        if hits > best_hits:
            best, best_hits = topic, hits
    # A greeting or thanks only wins when nothing else was asked.
    return best


def _city_in(text, locations):
    lowered = text.lower()
    return next((loc for loc in locations if loc.name.lower() in lowered), None)


# ---------- Answers ----------

def answer_prices(text, conversation):
    locations = list(Location.objects.active())
    city = _city_in(text, locations) or conversation.location
    cars = Car.objects.filter(is_active=True, location__is_active=True).select_related('location')
    if city:
        cars = cars.filter(location=city)
    cars = list(cars.order_by('price_per_day')[:5])
    if not cars:
        where = f' in {city.name}' if city else ''
        return (f"We don't have cars listed{where} right now. Tap “{TALK_TO_PERSON}” and we'll check for you.")
    lines = [f'• {c.name}: {kes(c.price_per_day)} per day' + ('' if city else f' ({c.location.name})') for c in cars]
    head = f'Our prices in {city.name}:' if city else 'Some of our prices:'
    return (f'{head}\n' + '\n'.join(lines) + '\n\n'
            f'Hire for 7+ days and some cars get a cheaper weekly rate. You can book with as little as '
            f'{kes(settings.BOOKING_MIN_FEE)} by M-Pesa and pay the rest at pick-up.\n'
            f'See every car and the total for your dates: {_url("fleet:cars")}')


def answer_booking(text, conversation):
    return ('Booking takes about 2 minutes:\n'
            '1. Open a car and tap “Book this car”.\n'
            '2. Pick your dates and times, then enter your name, M-Pesa number, ID and driving licence.\n'
            f'3. Choose how much to pay now (from {kes(settings.BOOKING_MIN_FEE)}) and approve the M-Pesa prompt '
            'on your phone.\n'
            "You're booked the moment you pay, and you get a receipt straight away.\n"
            f'Start here: {_url("fleet:cars")}')


def answer_payment(text, conversation):
    till = settings.BUSINESS.get('till_number')
    name = settings.BUSINESS.get('till_name') or settings.BUSINESS.get('name')
    till_line = f' The prompt shows {name}' + (f' (till {till})' if till else '') + '.' if name else ''
    return ('We take M-Pesa. When you book, we send a payment prompt to your phone; enter your M-Pesa PIN to '
            f'confirm.{till_line}\n'
            f'You can pay as little as {kes(settings.BOOKING_MIN_FEE)} to book (some bigger cars ask a bit more), '
            'or the full amount. Whatever is left is paid when you pick up the car.\n'
            "Didn't get the prompt? Make sure your phone is on and unlocked, then tap “Send the prompt again”.")


def answer_documents(text, conversation):
    return ('Please bring:\n'
            '• Your national ID or passport\n'
            '• Your valid driving licence\n'
            'You enter both numbers when you book. For anything else about requirements, '
            f'tap “{TALK_TO_PERSON}”.')


def answer_locations(text, conversation):
    locations = list(Location.objects.active().prefetch_related('pickup_points'))
    if not locations:
        return f'Tap “{TALK_TO_PERSON}” and we’ll tell you where to collect your car.'
    city = _city_in(text, locations)
    if city:
        points = [p for p in city.pickup_points.all() if p.is_active]
        lines = [f'• {p.name}' + (f' (+{kes(p.fee)})' if p.fee else ' (free)') for p in points]
        address = f'\nBranch: {city.address}' if city.address else ''
        return (f'In {city.name} you can collect your car from:\n' + ('\n'.join(lines) or '• Our branch')
                + address + f'\nCars in {city.name}: {settings.SITE_URL}{city.get_absolute_url()}')
    names = ', '.join(loc.name for loc in locations)
    return (f'We have branches in {names}. In each city you can collect from the branch, and in most from the '
            'airport or your hotel for a small fee. Some routes allow a one-way return to another city.\n'
            'Which city are you in?')


def answer_hours(text, conversation):
    return (f'Pick-ups and returns are from {_hours()}, every day. You can book online any time.')


def answer_contact(text, conversation):
    line = _contact_line()
    return (f'You can {line}' if line else 'You can reach us right here in the chat') + \
        f', or tap “{TALK_TO_PERSON}” and a team member will reply here.'


def answer_mybooking(text, conversation):
    ref = REF_RE.search(text)
    lead = f'To see booking {ref.group(0).upper()}' if ref else 'To see your booking'
    return (f'{lead} and download the receipt, go to {_url("bookings:find")} and enter the booking number '
            'and the phone number you booked with. The link in your confirmation email works too.')


def answer_greeting(text, conversation):
    return ('I can answer questions about prices, booking, M-Pesa payment, documents and our branches. '
            f'What would you like to know? Or tap “{TALK_TO_PERSON}” any time.')


def answer_thanks(text, conversation):
    return f'You’re welcome! Anything else? You can also tap “{TALK_TO_PERSON}”.'


ANSWERS = {
    'prices': answer_prices, 'booking': answer_booking, 'payment': answer_payment, 'documents': answer_documents,
    'locations': answer_locations, 'hours': answer_hours, 'contact': answer_contact, 'mybooking': answer_mybooking,
    'greeting': answer_greeting, 'thanks': answer_thanks,
}

FALLBACK = ("I'm the automatic assistant and I didn't quite get that. Ask me about prices, booking, payment, "
            f'documents or branches, or tap “{TALK_TO_PERSON}” and a team member will reply here.')


def handover_message(conversation):
    if agent_online():
        return ("I've asked a team member to join. They'll reply here in a few minutes, so keep this chat open.")
    contact = _contact_line()
    now = timezone.localtime().time()
    open_now = settings.BUSINESS_OPEN_TIME <= now <= settings.BUSINESS_CLOSE_TIME
    when = ('No one is at the desk this minute, but the team has been alerted and will reply here as soon as they can.'
            if open_now else
            f'Our team is offline now (we’re open {_hours()}). They’ve been alerted and will reply here '
            'when they’re back.')
    return when + (f' For anything urgent, {contact}.' if contact else '')


# ---------- Conversation rules ----------

def is_active(conversation):
    """The assistant speaks only until a person takes over."""
    if conversation.wants_agent:
        return False
    return not conversation.messages.filter(sender=Message.Sender.ADMIN).exists()


def _recent_fallbacks(conversation):
    count = 0
    for m in conversation.messages.filter(sender=Message.Sender.BOT).order_by('-id')[:FALLBACK_LIMIT]:
        if not m.body.endswith(FALLBACK):
            break
        count += 1
    return count


def reply_to(conversation, text, first=False):
    """
    Works out the assistant's reply to a visitor message.
    Returns (body, wants_person). body is None when the assistant should stay quiet.
    """
    if not is_active(conversation):
        return None, False
    topic = match_topic(text)
    hello = f'Hi {conversation.name.split()[0]}! ' if first else ''
    if topic == 'agent':
        return hello + handover_message(conversation), True
    if topic == 'changes':
        return (hello + 'Changes, cancellations and refunds are handled by our team. '
                + handover_message(conversation)), True
    if topic in ANSWERS:
        return hello + ANSWERS[topic](text, conversation), False
    if _recent_fallbacks(conversation) + 1 >= FALLBACK_LIMIT:
        return hello + 'Let me get a person to help. ' + handover_message(conversation), True
    return hello + FALLBACK, False
