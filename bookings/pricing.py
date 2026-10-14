"""
The one place booking totals are worked out. The booking popup asks the server for a quote, and
create_booking recalculates it again, so prices and day counts sent from the browser are never used.

Day rule: every started 24 hours counts as a day. Mon 10:00 to Thu 10:00 is 3 days; returning at
10:30 on Thu makes it 4.
"""
import math
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta

from django.conf import settings
from django.contrib.humanize.templatetags.humanize import intcomma
from django.utils import timezone

from fleet.models import Extra, Location, OneWayRoute

DEFAULT_TIME = time(10, 0)
TIME_STEP_MINUTES = 30
RATE_LABELS = {'weekly': ' (weekly rate)', 'monthly': ' (monthly rate)'}


class QuoteError(Exception):
    def __init__(self, message, field=None):
        super().__init__(message)
        self.message = message
        self.field = field


def kes(amount):
    return f'KES {intcomma(amount)}'


def time_choices():
    """Pick-up and return times every 30 minutes within business hours."""
    open_t, close_t = settings.BUSINESS_OPEN_TIME, settings.BUSINESS_CLOSE_TIME
    current = datetime.combine(datetime.min, open_t)
    end = datetime.combine(datetime.min, close_t)
    choices = []
    while current <= end:
        choices.append(current.time())
        current += timedelta(minutes=TIME_STEP_MINUTES)
    return choices


def default_time():
    choices = time_choices()
    return DEFAULT_TIME if DEFAULT_TIME in choices else (choices[0] if choices else DEFAULT_TIME)


def parse_time(value, label):
    """'10:30' -> time(10, 30), checked against business hours. None/blank -> the default time."""
    if isinstance(value, time):
        parsed = value
    elif not str(value or '').strip():
        return default_time()
    else:
        try:
            hours, minutes = (int(p) for p in str(value).strip().split(':')[:2])
            parsed = time(hours, minutes)
        except (TypeError, ValueError):
            raise QuoteError(f'Choose a {label} time.', field=f'{label.replace("-", "")}_time')
    if parsed not in time_choices():
        raise QuoteError(
            f'Choose a {label} time between {settings.BUSINESS_OPEN_TIME:%H:%M} and '
            f'{settings.BUSINESS_CLOSE_TIME:%H:%M}, on the hour or half hour.',
            field=f'{label.replace("-", "")}_time',
        )
    return parsed


def count_days(start, start_time, end, end_time):
    """Every started 24 hours counts as a day."""
    hours = (datetime.combine(end, end_time) - datetime.combine(start, start_time)).total_seconds() / 3600
    return max(math.ceil(hours / 24), 0)


def daily_rate_for(car, days):
    """
    The price per day for a hire of this length, and which rate it is. Hires of 30+ days use the
    monthly price and 7+ days the weekly price (per day), when the car has one and it's cheaper.
    """
    if days >= 30 and car.monthly_daily_rate and car.monthly_daily_rate < car.price_per_day:
        return car.monthly_daily_rate, 'monthly'
    if days >= 7 and car.weekly_daily_rate and car.weekly_daily_rate < car.price_per_day:
        return car.weekly_daily_rate, 'weekly'
    return car.price_per_day, 'daily'


def price_lines(days, daily_rate, pickup_point=None, pickup_fee=0, return_location=None, one_way_fee=0,
                extras=0, extra_items=None, rate_type='daily'):
    """The receipt breakdown as [{'label', 'amount'}], ending with the total."""
    rental = days * daily_rate
    lines = [{'label': f'{days} day{"s" if days != 1 else ""} x {kes(daily_rate)}{RATE_LABELS.get(rate_type, "")}',
              'amount': rental}]
    if extra_items:
        lines += [{'label': label, 'amount': amount} for label, amount in extra_items]
    elif extras:
        lines.append({'label': 'Extras', 'amount': extras})
    if pickup_point is not None:
        lines.append({'label': f'Pick-up at {pickup_point.name}', 'amount': pickup_fee})
    elif pickup_fee:
        lines.append({'label': 'Pick-up fee', 'amount': pickup_fee})
    if return_location is not None or one_way_fee:
        city = return_location.name if return_location is not None else 'another city'
        lines.append({'label': f'One-way return to {city}', 'amount': one_way_fee})
    lines.append({'label': 'Total', 'amount': rental + extras + pickup_fee + one_way_fee, 'total': True})
    return lines


@dataclass
class Quote:
    car: object
    start: object
    start_time: time
    end: object
    end_time: time
    days: int
    daily_rate: int
    rate_type: str
    pickup_point: object
    pickup_fee: int
    return_location: Location
    one_way_fee: int
    extra_items: list = field(default_factory=list)  # [(Extra, amount)]

    @property
    def extras(self):
        return sum(amount for _, amount in self.extra_items)

    @property
    def is_one_way(self):
        return self.return_location.pk != self.car.location_id

    @property
    def rental(self):
        return self.days * self.daily_rate

    @property
    def total(self):
        return self.rental + self.extras + self.pickup_fee + self.one_way_fee

    def lines(self):
        items = [(f'{e.name} ({kes(e.price)}/day)' if e.per_day else e.name, amount)
                 for e, amount in self.extra_items]
        return price_lines(
            self.days, self.daily_rate, self.pickup_point, self.pickup_fee,
            self.return_location if self.is_one_way else None, self.one_way_fee, self.extras, items,
            self.rate_type,
        )

    @property
    def min_pay(self):
        """Smallest amount that books the car: the car's booking fee, or the whole total if that is less."""
        return min(self.car.booking_fee, self.total)

    def pay_now(self, value):
        """
        The amount the customer chose to pay when booking, checked against this quote.
        Blank means the full total. Raises QuoteError (field 'pay_now') when it is out of range.
        """
        raw = str(value if value is not None else '').replace(',', '').replace('KES', '').strip()
        if not raw:
            return self.total
        try:
            amount = int(raw)
        except ValueError:
            raise QuoteError('Enter the amount to pay now in whole shillings, like 1000.', field='pay_now')
        if amount < self.min_pay:
            raise QuoteError(f'The smallest amount that books this car is {kes(self.min_pay)}.', field='pay_now')
        if amount > self.total:
            raise QuoteError(f'That is more than the total of {kes(self.total)}.', field='pay_now')
        return amount

    def as_dict(self):
        return {
            'total': self.total, 'days': self.days, 'breakdown': self.lines(), 'one_way': self.is_one_way,
            'min_pay': self.min_pay,
            'pickup': when(self.start, self.start_time),
            'return': when(self.end, self.end_time),
        }


def when(day, at=None):
    """'Mon 3 Nov 10:00' (written out by hand: %-d isn't supported on Windows)."""
    text = f'{day:%a} {day.day} {day:%b}'
    return f'{text} {at:%H:%M}' if at else text


def _lookup(model, value, **filters):
    """Finds a row by primary key or slug. Returns None for blank values."""
    value = str(value or '').strip()
    if not value:
        return None
    if value.isdigit():
        return model.objects.filter(pk=int(value), **filters).first()
    if hasattr(model, 'slug'):
        return model.objects.filter(slug=value, **filters).first()
    return None


def _extra_ids(raw):
    if raw in (None, ''):
        return []
    if isinstance(raw, (list, tuple)):
        values = raw
    else:
        values = str(raw).split(',')
    ids = []
    for value in values:
        value = str(value).strip()
        if not value.isdigit():
            raise QuoteError('One of the extras you chose is no longer offered. Untick it and try again.',
                             field='extras')
        ids.append(int(value))
    return sorted(set(ids))


def quote(car, start, end, pickup_point_id=None, return_location_id=None, extras=None,
          pickup_time=None, return_time=None, allow_past=False):
    """
    Prices a hire of `car`. Raises QuoteError if the dates, times or choices aren't allowed: a pick-up
    point not at the car's branch, a one-way return without an active route, an extra no longer offered.
    """
    start_time = parse_time(pickup_time, 'pick-up')
    end_time = parse_time(return_time, 'return')
    if end <= start:
        raise QuoteError('Choose a return date after the pick-up date.', field='return_date')
    if not allow_past:
        now = timezone.localtime()
        if datetime.combine(start, start_time) < now.replace(tzinfo=None):
            raise QuoteError('That pick-up time has already passed. Choose a later time or date.',
                             field='pickup_time')
    days = count_days(start, start_time, end, end_time)
    if days < settings.MIN_RENTAL_DAYS:
        raise QuoteError(f'The minimum hire is {settings.MIN_RENTAL_DAYS} day'
                         f'{"s" if settings.MIN_RENTAL_DAYS != 1 else ""}. Choose a later return date.',
                         field='return_date')
    if days > settings.MAX_RENTAL_DAYS:
        raise QuoteError(f'For rentals longer than {settings.MAX_RENTAL_DAYS} days, chat with us for a monthly rate.',
                         field='return_date')

    home = car.location
    points = home.pickup_points.filter(is_active=True)
    point = None
    if str(pickup_point_id or '').strip():
        point = points.filter(pk=int(pickup_point_id)).first() if str(pickup_point_id).isdigit() else None
        if point is None:
            raise QuoteError(f'Choose a pick-up point in {home.name}.', field='pickup_point')
    elif points.exists():
        raise QuoteError(f'Choose a pick-up point in {home.name}.', field='pickup_point')

    return_location = home
    one_way_fee = 0
    wanted = _lookup(Location, return_location_id)
    if str(return_location_id or '').strip() and wanted is None:
        raise QuoteError("We don't have a branch there. Choose another return city.", field='return_location')
    if wanted is not None and wanted.pk != home.pk:
        route = OneWayRoute.objects.filter(
            from_location=home, to_location=wanted, is_active=True, to_location__is_active=True
        ).first()
        if route is None:
            raise QuoteError(
                f"One-way returns from {home.name} to {wanted.name} aren't available. "
                'Choose another return city, or chat with us.', field='return_location'
            )
        return_location = wanted
        one_way_fee = route.fee

    ids = _extra_ids(extras)
    chosen = list(Extra.objects.active().filter(pk__in=ids))
    if len(chosen) != len(ids):
        raise QuoteError('One of the extras you chose is no longer offered. Untick it and try again.',
                         field='extras')

    daily_rate, rate_type = daily_rate_for(car, days)
    return Quote(
        car=car, start=start, start_time=start_time, end=end, end_time=end_time, days=days,
        daily_rate=daily_rate, rate_type=rate_type, pickup_point=point, pickup_fee=point.fee if point else 0,
        return_location=return_location, one_way_fee=one_way_fee,
        extra_items=[(extra, extra.cost(days)) for extra in chosen],
    )
