"""
Mobile app API, staff side (/api/v1/staff/). The app signs in once and sends "Authorization: Token <key>".
Branch staff only ever see their branch, exactly as in the web dashboard; the dashboard's own JSON views are
reused where they exist.
"""
from functools import wraps

from django.conf import settings

from django.contrib.auth import authenticate
from django.core.paginator import Paginator
from django.db.models import Prefetch
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from bookings import services, tokens
from bookings.models import Booking, BookingEvent
from bookings.pricing import QuoteError
from bookings.utils import rate_limited
from dashboard import car_views
from dashboard import views as dash
from dashboard.booking_views import _allowed, _in_city, filtered_bookings
from dashboard.models import staff_location
from fleet.models import Location
from fleet.utils import parse_date

from .models import ApiToken
from .views import body, car_json, error

Status = Booking.Status
PER_PAGE = 25


def token_auth(view):
    """Signs the request in as the token's staff member. No cookies are involved, so no CSRF check is needed."""
    @csrf_exempt
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        header = request.headers.get('Authorization', '')
        raw = header[6:].strip() if header.startswith('Token ') else ''
        token = ApiToken.find(raw)
        if token is None:
            return error('Your sign-in has ended. Sign in again.', 401)
        request.user = token.user
        request.api_token = token
        return view(request, *args, **kwargs)
    return wrapper


def me(user):
    branch = staff_location(user)
    return {
        'username': user.get_username(), 'name': user.get_full_name() or user.get_username(),
        'branch': {'slug': branch.slug, 'name': branch.name} if branch else None,
        'is_owner': branch is None,
        'branches': [] if branch else [{'slug': loc.slug, 'name': loc.name} for loc in Location.objects.all()],
    }


def viewing(request):
    """Branch staff: their branch. The owner: ?city=<slug>, or all of Kenya."""
    own = staff_location(request.user)
    if own is not None:
        return own
    slug = request.GET.get('city')
    return Location.objects.filter(slug=slug).first() if slug else None


# ---------- Sign in and out ----------

@csrf_exempt
@require_POST
def login(request):
    if rate_limited(request, 'api-login', limit=10, window_seconds=600):
        return error('Too many sign-in attempts. Wait 10 minutes and try again.', 429)
    data = body(request)
    user = authenticate(request, username=str(data.get('username') or '').strip(),
                        password=str(data.get('password') or ''))
    if user is None or not (user.is_active and user.is_staff):
        return error("That username and password don't match a staff account.", 400)
    token, raw = ApiToken.issue(user, str(data.get('device') or ''))
    return JsonResponse({'token': raw, 'user': me(user)}, status=201)


@token_auth
@require_POST
def logout(request):
    request.api_token.delete()
    return JsonResponse({'ok': True})


@token_auth
@require_GET
def profile(request):
    return JsonResponse({'user': me(request.user)})


# ---------- Overview and bookings ----------

@token_auth
@require_GET
def overview(request):
    today = timezone.localdate()
    city = viewing(request)
    qs = _in_city(dash.scoped_bookings(request.user), city)
    active = qs.filter(status__in=(Status.PAID, Status.PICKED_UP))
    rows = lambda items: [b.admin_dict() for b in items]   # noqa: E731
    return JsonResponse({
        'today': today.isoformat(),
        'city': city.slug if city else '',
        'stats': dash._stats(city, request.user),
        'pickups': rows(active.filter(pickup_date=today).order_by('pickup_time')),
        'returns': rows(active.filter(return_date=today).order_by('return_time')),
        'out': rows(dash.out_now(qs, today).order_by('return_date', 'return_time')),
        'awaiting': rows(qs.blocking().filter(status=Status.PENDING).order_by('-created_at')),
        'latest': rows(qs.order_by('-created_at')[:10]),
    })


@token_auth
@require_GET
def bookings(request):
    """The dashboard's search and filters: q, status, car, city (owner), from, to, sort; 25 a page."""
    qs, _, sort = filtered_bookings(request)
    page = Paginator(qs, PER_PAGE).get_page(request.GET.get('page'))
    return JsonResponse({
        'results': [b.admin_dict() for b in page], 'page': page.number, 'pages': page.paginator.num_pages,
        'total': page.paginator.count, 'sort': sort,
        'statuses': [{'value': v, 'label': lbl} for v, lbl in Status.choices],
    })


def _detail(booking):
    return {
        **booking.admin_dict(),
        'id_number': booking.id_number, 'licence_number': booking.licence_number,
        'whatsapp_link': booking.whatsapp_link,
        'allowed': _allowed(booking),
        **tokens.links(booking, absolute=settings.SITE_URL),   # signed receipt and calendar links
        'events': [{'kind': e.kind, 'label': e.get_kind_display(), 'who': e.who, 'message': e.message,
                    'at': timezone.localtime(e.created_at).strftime('%d %b, %H:%M')} for e in booking.events.all()],
        'payments': [{'status': p.status, 'label': p.get_status_display(), 'amount': p.amount, 'phone': p.masked_phone,
                      'receipt': p.mpesa_receipt, 'result': p.result_desc,
                      'at': timezone.localtime(p.created_at).strftime('%d %b, %H:%M')} for p in booking.payments.all()],
    }


def _booking(request, ref):
    qs = dash.scoped_bookings(request.user).prefetch_related(
        'extras', 'payments', Prefetch('events', queryset=BookingEvent.objects.select_related('user')))
    return get_object_or_404(qs, ref=ref)


@token_auth
@require_GET
def booking_detail(request, ref):
    return JsonResponse({'booking': _detail(_booking(request, ref))})


@token_auth
@require_POST
def booking_action(request, ref):
    """
    The dashboard's booking actions: pickup, return, cancel (reason), mark_paid (code), balance (amount, code),
    resend, note (note), relocate, preview_dates / change_dates (pickup_date, pickup_time, return_date, return_time).
    """
    booking = _booking(request, ref)
    data = body(request)
    action = data.get('action')
    user = request.user
    try:
        if action == 'pickup':
            services.mark_picked_up(booking, user)
        elif action == 'return':
            services.mark_returned(booking, user)
        elif action == 'cancel':
            services.cancel_booking(booking, user, data.get('reason'))
        elif action == 'mark_paid':
            services.mark_paid_manually(booking, user, data.get('code'))
        elif action == 'balance':
            services.record_balance_payment(booking, user, data.get('amount'), data.get('code'))
        elif action == 'resend':
            services.resend_confirmation(booking, user)
        elif action == 'note':
            services.add_note(booking, user, data.get('note'))
        elif action == 'relocate':
            services.relocate_car(booking, user)
        elif action in ('preview_dates', 'change_dates'):
            start, end = parse_date(data.get('pickup_date')), parse_date(data.get('return_date'))
            start_time, end_time = data.get('pickup_time'), data.get('return_time')
            if action == 'preview_dates':
                try:
                    preview = services.date_change_quote(booking, start, start_time, end, end_time)
                except QuoteError as exc:
                    return error(exc.message)
                return JsonResponse({'preview': preview})
            services.change_dates(booking, user, start, start_time, end, end_time)
        else:
            return error('Unknown action.')
    except services.ActionError as exc:
        return error(str(exc))
    return JsonResponse({'booking': _detail(_booking(request, ref))})


# ---------- Cars ----------

@token_auth
@require_GET
def cars(request):
    items = dash.scoped_cars(request.user).prefetch_related('photos').order_by('location__display_order', 'name')
    return JsonResponse({'cars': [{**car_json(request, c), 'is_active': c.is_active, 'units': c.units}
                                  for c in items]})


@token_auth
@require_POST
def car_toggle(request, pk):
    """Shows or hides a car on the website and in the app."""
    car = get_object_or_404(dash.scoped_cars(request.user), pk=pk)
    car.is_active = not car.is_active
    car.save(update_fields=['is_active'])
    return JsonResponse({'id': car.pk, 'is_active': car.is_active})


# The dashboard's JSON views, signed in with the app token instead of a browser session.
feed = token_auth(dash.api_feed)
chats = token_auth(dash.api_chats)
chat_messages = token_auth(dash.api_chat_messages)
chat_reply = token_auth(dash.api_chat_reply)
chat_assign = token_auth(dash.api_chat_assign)
photo_upload = token_auth(car_views.photo_upload)
