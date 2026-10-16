"""
Mobile app API, customer side (/api/v1/). No cookies: a booking is opened with its signed token (the same one
the emailed links carry), a chat with its long random id. Prices, availability and payments go through the
same code as the website.
"""
import json
from datetime import timedelta

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from bookings import tokens
from bookings.models import Booking
from bookings.pricing import default_time, time_choices
from bookings.services import BookingRequestError, check_pending_payment, place_booking, retry_booking_payment
from bookings.utils import normalize_phone, rate_limited
from fleet.models import Car, Extra, Location
from fleet.utils import search_dates
from fleet.views import (SEAT_CHOICES, SORT_CHOICES, _cars_for, _nearby_with_cars, _pick_location,
                         apply_car_filters, car_filters)

CALENDAR_DAYS = 366


def error(message, status=400, **extra):
    return JsonResponse({'error': message, **extra}, status=status)


def body(request):
    try:
        data = json.loads(request.body or b'{}')
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def absolute(request, url):
    return request.build_absolute_uri(url) if url else ''


# ---------- Shapes ----------

def location_json(loc, with_points=False):
    data = {
        'slug': loc.slug, 'name': loc.name, 'city': loc.city, 'county': loc.county, 'address': loc.address,
        'opening_hours': loc.opening_hours, 'phone': loc.contact_phone, 'whatsapp': loc.whatsapp_link,
        'maps_url': loc.maps_url,
        'latitude': float(loc.latitude) if loc.latitude is not None else None,
        'longitude': float(loc.longitude) if loc.longitude is not None else None,
    }
    if with_points:
        data['pickup_points'] = [{'id': p.pk, 'name': p.name, 'fee': p.fee}
                                 for p in loc.pickup_points.filter(is_active=True)]
        data['routes'] = [{'to': r.to_location.slug, 'name': r.to_location.name, 'fee': r.fee}
                          for r in loc.one_way_routes()]
    return data


def car_json(request, car, days=None):
    cover = car.cover
    data = {
        'id': car.pk, 'name': car.name,
        'category': car.category, 'category_label': car.get_category_display(),
        'transmission': car.transmission, 'transmission_label': car.get_transmission_display(),
        'fuel': car.fuel, 'fuel_label': car.get_fuel_display(),
        'seats': car.seats, 'doors': car.doors, 'luggage': car.luggage, 'engine_size': car.engine_size,
        'air_con': car.air_con,
        'price_per_day': car.price_per_day, 'weekly_rate': car.weekly_rate, 'monthly_rate': car.monthly_rate,
        'booking_fee': car.booking_fee,
        'location': {'slug': car.location.slug, 'name': car.location.name},
        'photo': absolute(request, cover.thumbnail.url) if cover else '',
        'web_url': settings.SITE_URL + car.get_absolute_url(),
    }
    if days is not None:
        data.update(days=days, available=car.available, total=car.total, rate_type=car.rate_type)
    return data


def booking_json(booking):
    """What the customer's phone keeps: the booking, its access token and its links."""
    cover = booking.car.cover
    return {
        **booking.public_dict(),
        'token': tokens.booking_token(booking.ref),
        'car_id': booking.car_id,
        'car_photo': settings.SITE_URL + cover.thumbnail.url if cover else '',
        **tokens.links(booking, absolute=settings.SITE_URL),
    }


def booking_from_token(request, ref):
    """The booking, or None when the token (header X-Booking-Token or ?t=) doesn't match."""
    booking = get_object_or_404(Booking.objects.with_details(), ref=ref)
    token = request.headers.get('X-Booking-Token') or request.GET.get('t')
    return booking if tokens.check_token(booking.ref, token) else None


# ---------- Setup ----------

@require_GET
def config(request):
    """Everything the app needs once at start: branches, extras, booking rules, contact details."""
    from bookings.services import NO_RESPONSE_SECONDS

    biz = settings.BUSINESS
    return JsonResponse({
        'business': {'name': biz['name'], 'phone': biz['phone'], 'whatsapp': biz['whatsapp'], 'email': biz['email'],
                     'till_name': biz['till_name'], 'site_url': settings.SITE_URL},
        'branches': [location_json(loc, with_points=True) for loc in Location.objects.active()],
        'extras': [{'id': e.pk, 'name': e.name, 'description': e.description, 'price': e.price, 'per_day': e.per_day}
                   for e in Extra.objects.active()],
        'categories': [{'value': v, 'label': lbl} for v, lbl in Car.Category.choices],
        'transmissions': [{'value': v, 'label': lbl} for v, lbl in Car.Transmission.choices],
        'seat_choices': [{'value': v, 'label': lbl} for v, lbl in SEAT_CHOICES],
        'sort_choices': [{'value': v, 'label': lbl} for v, lbl in SORT_CHOICES],
        'booking': {
            'times': [t.strftime('%H:%M') for t in time_choices()],
            'default_time': default_time().strftime('%H:%M'),
            'min_days': settings.MIN_RENTAL_DAYS, 'max_days': settings.MAX_RENTAL_DAYS,
            'min_fee': settings.BOOKING_MIN_FEE, 'prompt_seconds': NO_RESPONSE_SECONDS,
            'hold_minutes': settings.BOOKING_HOLD_MINUTES,
        },
        'links': {'terms': f'{settings.SITE_URL}/terms/', 'privacy': f'{settings.SITE_URL}/privacy/',
                  'faq': f'{settings.SITE_URL}/faq/'},
    })


# ---------- Cars ----------

@require_GET
def cars(request):
    """Cars at one branch for the dates, with the same filters and sorting as the website's car list."""
    active = list(Location.objects.active())
    location = _pick_location(request.GET.get('city', ''), active)
    if location is None:
        return JsonResponse({'location': None, 'cars': [], 'suggestions': []})
    start, end = search_dates(request.GET.get('from'), request.GET.get('to'))
    category = request.GET.get('category', '')
    if category not in Car.Category.values:
        category = ''
    days = (end - start).days
    all_cars = _cars_for(location, start, end, category)
    filtered = apply_car_filters(list(all_cars), car_filters(request))
    suggestions = []
    if not any(c.available for c in filtered):
        suggestions = [{'slug': c.slug, 'name': c.name, 'free_cars': c.free_cars,
                        'distance_km': round(c.distance) if c.distance else None}
                       for c in _nearby_with_cars(location, active, start, end, category)]
    return JsonResponse({
        'location': location_json(location),
        'from': start.isoformat(), 'to': end.isoformat(), 'days': days,
        'total_count': len(all_cars),
        'cars': [car_json(request, c, days) for c in filtered],
        'suggestions': suggestions,
    })


@require_GET
def car_detail(request, pk):
    car = get_object_or_404(Car.objects.select_related('location').prefetch_related('photos'),
                            pk=pk, is_active=True, location__is_active=True)
    start, end = search_dates(request.GET.get('from'), request.GET.get('to'))
    prices = [{'label': '1 to 6 days', 'per_day': car.price_per_day, 'note': 'per day'}]
    if car.weekly_rate:
        prices.append({'label': '7 to 29 days', 'per_day': car.weekly_daily_rate,
                       'note': f'per day (KES {car.weekly_rate:,} a week)'})
    if car.monthly_rate:
        prices.append({'label': '30 days or more', 'per_day': car.monthly_daily_rate,
                       'note': f'per day (KES {car.monthly_rate:,} a month)'})
    today = timezone.localdate()
    return JsonResponse({
        'car': {
            **car_json(request, car),
            'description': car.description,
            'features': list(car.feature_labels),
            'photos': [{'url': absolute(request, p.image.url), 'thumb': absolute(request, p.thumbnail.url),
                        'width': p.width, 'height': p.height} for p in car.photos.all()],
            'prices': prices,
        },
        'branch': location_json(car.location, with_points=True),
        'unavailable': [d.isoformat() for d in car.unavailable_dates(today, today + timedelta(days=CALENDAR_DAYS))],
        'from': start.isoformat(), 'to': end.isoformat(),
    })


# ---------- Bookings ----------

@csrf_exempt
@require_POST
def booking_create(request):
    if rate_limited(request, 'book', limit=6, window_seconds=300):
        return error('Too many booking attempts. Wait a few minutes and try again.', 429)
    try:
        booking = place_booking(body(request), channel='app')
    except BookingRequestError as exc:
        if exc.booking:
            return error(exc.message, exc.status, booking=booking_json(exc.booking))
        return error(exc.message, exc.status, **({'field': exc.field} if exc.field else {}))
    return JsonResponse({'booking': booking_json(booking)}, status=201)


@require_GET
def booking_status(request, ref):
    booking = booking_from_token(request, ref)
    if booking is None:
        return error("This booking can't be opened on this phone. Find it with its number and phone number.", 403)
    return JsonResponse({'booking': booking_json(check_pending_payment(booking))})


@csrf_exempt
@require_POST
def booking_retry(request, ref):
    if rate_limited(request, f'retry:{ref}', limit=4, window_seconds=600):
        return error('Too many attempts. Wait a few minutes, or chat with us for help.', 429)
    booking = booking_from_token(request, ref)
    if booking is None:
        return error("This booking can't be opened on this phone.", 403)
    try:
        booking = retry_booking_payment(booking)
    except BookingRequestError as exc:
        if exc.booking:
            return error(exc.message, exc.status, booking=booking_json(exc.booking))
        return error(exc.message, exc.status)
    return JsonResponse({'booking': booking_json(booking)})


@csrf_exempt
@require_POST
def booking_find(request):
    """Booking number + the phone that paid returns the booking and its token (so it can be saved on the phone)."""
    if rate_limited(request, 'find', limit=10, window_seconds=600):
        return error('Too many tries. Wait 10 minutes, or chat with us and we will find your booking.', 429)
    data = body(request)
    ref = str(data.get('ref') or '').strip().upper().replace(' ', '')
    phone = normalize_phone(str(data.get('phone') or ''))
    booking = Booking.objects.with_details().filter(ref=ref).first() if ref else None
    if not (booking and phone and booking.phone == phone):
        return error("We couldn't find a booking with that number and phone. Check both: the booking number starts "
                     'with ZCH, and the phone is the one you paid with.', 404)
    return JsonResponse({'booking': booking_json(check_pending_payment(booking))})
