from datetime import timedelta

from django.conf import settings
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET

from bookings.pricing import daily_rate_for
from pages.content import faq

from .models import Car, Extra, Location
from .seo import branch_jsonld
from .utils import search_dates

DEFAULT_CITY = 'nairobi'
FEATURED = 6
MAX_SUGGESTIONS = 3


def _pick_location(slug, active):
    """The searched city, else Nairobi, else the first active branch."""
    by_slug = {loc.slug: loc for loc in active}
    return by_slug.get(slug) or by_slug.get(DEFAULT_CITY) or (active[0] if active else None)


def _cars_for(location, start, end, category):
    cars = Car.objects.filter(is_active=True, location=location).select_related('location').prefetch_related('photos')
    if category:
        cars = cars.filter(category=category)
    days = (end - start).days
    car_list = []
    for car in cars:
        car.available = car.is_available(start, end)
        rate, car.rate_type = daily_rate_for(car, days)
        car.total = rate * days
        car_list.append(car)
    return car_list


def _nearby_with_cars(location, active, start, end, category):
    """Closest other branches with at least one car free for these dates."""
    found = []
    for other in active:
        if other.pk == location.pk:
            continue
        free = sum(1 for car in _cars_for(other, start, end, category) if car.available)
        if free:
            other.free_cars = free
            other.distance = location.distance_km(other)
            found.append(other)
    found.sort(key=lambda loc: (loc.distance is None, loc.distance or 0, loc.display_order))
    return found[:MAX_SUGGESTIONS]


def booking_flow_context(request):
    """What the booking popup needs on any page that can open it."""
    from bookings.pricing import default_time, time_choices
    from bookings.services import NO_RESPONSE_SECONDS

    return {
        'extras': list(Extra.objects.active()),
        'time_choices': time_choices(),
        'default_time': default_time(),
        'preselect_dates': bool(request.GET.get('from') and request.GET.get('to')),
        'min_days': settings.MIN_RENTAL_DAYS,
        'max_days': settings.MAX_RENTAL_DAYS,
        'prompt_seconds': NO_RESPONSE_SECONDS,
    }


def branch_context(request, location, active):
    """The branch's pick-up points and one-way routes, for the search bar and booking popup."""
    routes = list(location.one_way_routes()) if location else []
    wanted_return = request.GET.get('return_to', '')
    return {
        'location': location,
        'locations': active,
        'routes_by_city': {
            loc.slug: [{'slug': r.to_location.slug, 'name': r.to_location.name, 'fee': r.fee}
                       for r in loc.one_way_routes()]
            for loc in active
        },
        'routes': routes,
        'return_route': next((r for r in routes if r.to_location.slug == wanted_return), None),
        'pickup_points': list(location.pickup_points.filter(is_active=True)) if location else [],
    }


def _listing(request, location, active):
    """Search, cars and booking-dialog context shared by the home page and the city pages."""
    start, end = search_dates(request.GET.get('from'), request.GET.get('to'))
    category = request.GET.get('category', '')
    if category not in Car.Category.values:
        category = ''

    cars = _cars_for(location, start, end, category) if location else []
    suggestions = []
    if location and not any(car.available for car in cars):
        suggestions = _nearby_with_cars(location, active, start, end, category)

    return {
        **branch_context(request, location, active),
        'cars': cars,
        'suggestions': suggestions,
        'start': start,
        'end': end,
        'days': (end - start).days,
        **booking_flow_context(request),
        'category': category,
        'categories': Car.Category.choices,
        'today': timezone.localdate(),
    }


@ensure_csrf_cookie
def home(request):
    active = list(Location.objects.active())
    location = _pick_location(request.GET.get('city', ''), active)
    context = _listing(request, location, active)
    featured = sorted(context['cars'], key=lambda c: (not c.available, c.price_per_day))
    context.update({
        'featured': featured[:FEATURED],
        'explicit_city': bool(request.GET.get('city')),
        'jsonld': branch_jsonld(active, request),
        'faq': faq(settings),
    })
    return render(request, 'fleet/home.html', context)


@ensure_csrf_cookie
def city(request, slug):
    active = list(Location.objects.active())
    location = next((loc for loc in active if loc.slug == slug), None)
    if location is None:
        raise Http404('No branch here')
    context = _listing(request, location, active)
    context.update({'explicit_city': True, 'jsonld': branch_jsonld([location], request)})
    return render(request, 'fleet/city.html', context)


SEAT_CHOICES = [(2, '2 or more'), (5, '5 or more'), (7, '7 or more'), (8, '8 or more')]
SORT_CHOICES = [('recommended', 'Free cars first'), ('price_asc', 'Price: low to high'),
                ('price_desc', 'Price: high to low')]


def _int(value):
    try:
        return max(int(str(value).replace(',', '').strip()), 0)
    except (TypeError, ValueError):
        return None


def car_filters(request):
    g = request.GET
    transmission = g.get('transmission', '')
    sort = g.get('sort', '')
    return {
        'transmission': transmission if transmission in Car.Transmission.values else '',
        'seats': _int(g.get('seats')) if _int(g.get('seats')) in dict(SEAT_CHOICES) else None,
        'price_min': _int(g.get('price_min')),
        'price_max': _int(g.get('price_max')),
        'sort': sort if sort in dict(SORT_CHOICES) else 'recommended',
    }


def apply_car_filters(cars, f):
    if f['transmission']:
        cars = [c for c in cars if c.transmission == f['transmission']]
    if f['seats']:
        cars = [c for c in cars if c.seats >= f['seats']]
    if f['price_min'] is not None:
        cars = [c for c in cars if c.price_per_day >= f['price_min']]
    if f['price_max']:
        cars = [c for c in cars if c.price_per_day <= f['price_max']]
    if f['sort'] == 'price_asc':
        cars.sort(key=lambda c: (c.price_per_day, c.name))
    elif f['sort'] == 'price_desc':
        cars.sort(key=lambda c: (-c.price_per_day, c.name))
    else:
        cars.sort(key=lambda c: (not c.available, c.price_per_day, c.name))
    return cars


@ensure_csrf_cookie
def cars(request):
    """All cars at one branch, with filters. ?partial=1 returns just the results, for filtering without a reload."""
    active = list(Location.objects.active())
    location = _pick_location(request.GET.get('city', ''), active)
    context = _listing(request, location, active)
    filters = car_filters(request)
    context['all_cars_count'] = len(context['cars'])
    context['cars'] = apply_car_filters(context['cars'], filters)
    if not any(car.available for car in context['cars']) and not context['suggestions'] and location:
        context['suggestions'] = _nearby_with_cars(location, active, context['start'], context['end'],
                                                   context['category'])
    context.update({
        'filters': filters, 'seat_choices': SEAT_CHOICES, 'sort_choices': SORT_CHOICES,
        'transmissions': Car.Transmission.choices, 'explicit_city': bool(request.GET.get('city')),
    })
    template = 'fleet/_car_results.html' if request.GET.get('partial') else 'fleet/cars.html'
    return render(request, template, context)


@ensure_csrf_cookie
def car_detail(request, pk, slug):
    car = get_object_or_404(Car.objects.select_related('location').prefetch_related('photos'),
                            pk=pk, is_active=True, location__is_active=True)
    if slug != car.slug:
        return redirect(car.get_absolute_url(), permanent=True)
    active = list(Location.objects.active())
    start, end = search_dates(request.GET.get('from'), request.GET.get('to'))
    prices = [('1 to 6 days', car.price_per_day, 'per day')]
    if car.weekly_rate:
        prices.append(('7 to 29 days', car.weekly_daily_rate, f'per day (KES {car.weekly_rate:,} a week)'))
    if car.monthly_rate:
        prices.append(('30 days or more', car.monthly_daily_rate, f'per day (KES {car.monthly_rate:,} a month)'))
    context = {
        **branch_context(request, car.location, active),
        **booking_flow_context(request),
        'car': car,
        'photos': list(car.photos.all()),
        'prices': prices,
        'start': start,
        'end': end,
        'days': (end - start).days,
        'today': timezone.localdate(),
        'others': [c for c in _cars_for(car.location, start, end, '') if c.pk != car.pk][:3],
    }
    return render(request, 'fleet/car_detail.html', context)


@require_GET
def availability(request):
    """Lightweight endpoint the car list polls so 'Booked' badges update without a reload."""
    start, end = search_dates(request.GET.get('from'), request.GET.get('to'))
    cars = Car.objects.filter(is_active=True, location__is_active=True)
    if request.GET.get('city'):
        cars = cars.filter(location__slug=request.GET['city'])
    return JsonResponse({'available': {str(car.pk): car.is_available(start, end) for car in cars}})


MAX_CALENDAR_MONTHS = 12


@require_GET
def booked_dates(request, pk):
    """Days a car can't be picked up or kept over, for the booking calendar."""
    car = get_object_or_404(Car, pk=pk, is_active=True, location__is_active=True)
    try:
        months = min(max(int(request.GET.get('months', 6)), 1), MAX_CALENDAR_MONTHS)
    except ValueError:
        months = 6
    start = timezone.localdate()
    end = start + timedelta(days=months * 31)
    return JsonResponse({
        'car': car.pk,
        'units': car.units,
        'from': start.isoformat(),
        'to': end.isoformat(),
        'unavailable': [day.isoformat() for day in car.unavailable_dates(start, end)],
    })


@require_GET
def sitemap(request):
    today = timezone.localdate().isoformat()
    urls = [settings.SITE_URL + reverse(name) for name in (
        'fleet:home', 'fleet:cars', 'pages:faq', 'pages:about', 'pages:contact', 'pages:terms', 'pages:privacy')]
    urls += [settings.SITE_URL + loc.get_absolute_url() for loc in Location.objects.active()]
    urls += [settings.SITE_URL + car.get_absolute_url()
             for car in Car.objects.filter(is_active=True, location__is_active=True).select_related('location')]
    body = ''.join(f'<url><loc>{url}</loc><lastmod>{today}</lastmod></url>' for url in urls)
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>\n')
    return HttpResponse(xml, content_type='application/xml')


@require_GET
def robots(request):
    lines = ['User-agent: *', 'Disallow: /dashboard/', 'Disallow: /django-admin/', 'Disallow: /admin/', 'Disallow: /bookings/',
             f'Sitemap: {settings.SITE_URL}{reverse("fleet:sitemap")}']
    return HttpResponse('\n'.join(lines) + '\n', content_type='text/plain')
