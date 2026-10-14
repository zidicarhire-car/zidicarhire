import json
from datetime import date
from functools import wraps

from django.contrib import messages
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth import views as auth_views
from django.db.models import Count, F, Q, Sum
from django.db.models.functions import TruncMonth
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_GET, require_POST

from bookings.models import Booking
from bookings.services import (ActionError, cancel_booking, mark_paid_manually, mark_picked_up, mark_returned,
                               relocate_car)
from chat.models import Conversation, Message
from chat.services import mark_agent_online
from fleet.models import Car, Location, OneWayRoute
from payments.payhero import config_problems

from .forms import LocationForm, PickupPointFormSet, RouteFormSet
from .models import staff_location

DONE = list(Booking.PAID_STATES)
VIEW_CITY_KEY = 'dash_city'


def staff_page(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_authenticated and request.user.is_staff):
            return redirect(f"{reverse('dashboard:login')}?next={request.path}")
        return view(request, *args, **kwargs)
    return wrapper


def staff_api(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_authenticated and request.user.is_staff):
            return JsonResponse({'error': 'Your session ended. Sign in again.'}, status=401)
        return view(request, *args, **kwargs)
    return wrapper


def owner_page(view):
    """Branches and routes are managed by staff who see all of Kenya, not by branch staff."""
    @staff_page
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if staff_location(request.user) is not None:
            messages.error(request, 'Only the owner can change branches and routes.')
            return redirect('dashboard:home')
        return view(request, *args, **kwargs)
    return wrapper


class LoginView(auth_views.LoginView):
    template_name = 'dashboard/login.html'
    authentication_form = AdminAuthenticationForm  # only staff accounts can sign in
    redirect_authenticated_user = True


# ---------- Branch scoping ----------
# Staff tied to a branch only ever get that branch's rows. Everyone else can narrow the view to one
# city with the selector in the sidebar (kept in the session so it applies on every page).

def view_location(request):
    own = staff_location(request.user)
    if own is not None:
        return own
    pk = request.session.get(VIEW_CITY_KEY)
    return Location.objects.filter(pk=pk).first() if pk else None


def scoped_cars(user):
    loc = staff_location(user)
    qs = Car.objects.select_related('location')
    return qs.filter(location=loc) if loc else qs


def scoped_bookings(user):
    """A branch sees bookings collected there, and one-way hires being returned there."""
    loc = staff_location(user)
    qs = Booking.objects.with_details()
    return qs.filter(Q(pickup_location=loc) | Q(return_location=loc)) if loc else qs


def scoped_chats(user):
    loc = staff_location(user)
    qs = Conversation.objects.select_related('location')
    return qs.filter(location=loc) if loc else qs


def awaiting_relocation(qs):
    return qs.filter(status__in=DONE, car_relocated=False).exclude(return_location=F('pickup_location'))


def _ctx(request, **extra):
    own = staff_location(request.user)
    return {
        'staff_location': own,
        'view_location': view_location(request),
        'all_locations': Location.objects.all() if own is None else [],
        'is_owner': own is None,
        'payment_problems': config_problems(),
        **extra,
    }


@staff_page
@require_POST
def set_city(request):
    if staff_location(request.user) is None:
        pk = request.POST.get('city', '')
        if pk.isdigit() and Location.objects.filter(pk=pk).exists():
            request.session[VIEW_CITY_KEY] = int(pk)
        else:
            request.session.pop(VIEW_CITY_KEY, None)
    nxt = request.POST.get('next', '')
    if not url_has_allowed_host_and_scheme(nxt, {request.get_host()}, request.is_secure()):
        nxt = reverse('dashboard:home')
    return redirect(nxt)


# ---------- Pages ----------

@staff_page
@require_POST
def booking_relocate(request, ref):
    booking = get_object_or_404(scoped_bookings(request.user), ref=ref)
    booking, moved = relocate_car(booking, request.user)
    if moved:
        messages.success(request, f'{booking.car.name} is now listed in {booking.return_location}.')
    else:
        messages.info(request, 'That car was already moved.')
    return redirect('dashboard:cars')


@staff_page
def chats(request):
    return render(request, 'dashboard/chats.html', _ctx(request, nav='chats'))


def _month_starts(count):
    today = timezone.localdate()
    year, month = today.year, today.month
    months = []
    for _ in range(count):
        months.append(date(year, month, 1))
        year, month = (year, month - 1) if month > 1 else (year - 1, 12)
    return months


@staff_page
def reports(request):
    """Paid bookings and revenue per city per month, for the last 12 months."""
    viewing = view_location(request)
    months = _month_starts(12)
    cities = [viewing] if viewing else list(Location.objects.filter(
        Q(is_active=True) | Q(pickup_bookings__status__in=DONE)).distinct())

    qs = Booking.objects.filter(status__in=DONE, paid_at__date__gte=months[-1])
    if viewing:
        qs = qs.filter(pickup_location=viewing)
    totals = {}
    for row in (qs.annotate(month=TruncMonth('paid_at')).values('month', 'pickup_location')
                .annotate(n=Count('id'), revenue=Sum('amount_paid'))):
        key = (row['month'].year, row['month'].month)
        totals[key, row['pickup_location']] = (row['n'], row['revenue'] or 0)

    rows = []
    for m in months:
        cells = [totals.get(((m.year, m.month), city.pk), (0, 0)) for city in cities]
        rows.append({'month': m, 'cells': cells,
                     'n': sum(c[0] for c in cells), 'revenue': sum(c[1] for c in cells)})
    column_totals = [(sum(r['cells'][i][0] for r in rows), sum(r['cells'][i][1] for r in rows))
                     for i in range(len(cities))]
    return render(request, 'dashboard/reports.html', _ctx(
        request, nav='reports', cities=cities, rows=rows, column_totals=column_totals,
        grand_n=sum(r['n'] for r in rows), grand_revenue=sum(r['revenue'] for r in rows),
    ))


@owner_page
def locations(request):
    if request.method == 'POST':
        form = LocationForm(request.POST)
        if form.is_valid():
            loc = form.save()
            messages.success(request, f'{loc.name} branch added. Now add its pick-up points.')
            return redirect('dashboard:location_edit', pk=loc.pk)
    else:
        form = LocationForm()
    branches = Location.objects.annotate(
        car_count=Count('cars', filter=Q(cars__is_active=True), distinct=True),
        point_count=Count('pickup_points', filter=Q(pickup_points__is_active=True), distinct=True),
    )
    return render(request, 'dashboard/locations.html', _ctx(request, form=form, branches=branches, nav='branches'))


@owner_page
def location_edit(request, pk):
    loc = get_object_or_404(Location, pk=pk)
    if request.method == 'POST':
        form = LocationForm(request.POST, instance=loc)
        points = PickupPointFormSet(request.POST, instance=loc)
        if form.is_valid() and points.is_valid():
            form.save()
            points.save()
            messages.success(request, f'{loc.name} saved.')
            return redirect('dashboard:location_edit', pk=loc.pk)
    else:
        form = LocationForm(instance=loc)
        points = PickupPointFormSet(instance=loc)
    return render(request, 'dashboard/location_edit.html', _ctx(
        request, form=form, points=points, loc=loc, nav='branches'))


@owner_page
@require_POST
def location_toggle(request, pk):
    loc = get_object_or_404(Location, pk=pk)
    loc.is_active = not loc.is_active
    loc.save(update_fields=['is_active'])
    messages.success(request, f'{loc.name} is now {"shown on" if loc.is_active else "hidden from"} the website.')
    return redirect('dashboard:locations')


@owner_page
def routes(request):
    qs = OneWayRoute.objects.select_related('from_location', 'to_location')
    if request.method == 'POST':
        formset = RouteFormSet(request.POST, queryset=qs)
        if formset.is_valid():
            formset.save()
            messages.success(request, 'One-way routes saved.')
            return redirect('dashboard:routes')
    else:
        formset = RouteFormSet(queryset=qs)
    return render(request, 'dashboard/routes.html', _ctx(request, formset=formset, nav='routes'))


# ---------- JSON API used by dashboard.js ----------

def out_now(qs, today=None):
    """Cars with customers: marked picked up, or paid and inside their hire dates."""
    today = today or timezone.localdate()
    return qs.filter(Q(status=Booking.Status.PICKED_UP)
                     | Q(status=Booking.Status.PAID, pickup_date__lte=today, return_date__gt=today))


def _stats(viewing, user):
    today = timezone.localdate()
    qs = Booking.objects.all()
    if viewing:
        qs = qs.filter(pickup_location=viewing)
    paid = qs.filter(status__in=DONE)
    return {
        'paid_today': paid.filter(paid_at__date=today).count(),
        'revenue_today': paid.filter(paid_at__date=today).aggregate(total=Sum('amount_paid'))['total'] or 0,
        'revenue_month': paid.filter(
            paid_at__date__gte=today.replace(day=1)
        ).aggregate(total=Sum('amount_paid'))['total'] or 0,
        'on_the_road': out_now(qs, today).count(),
        'awaiting_payment': qs.blocking().filter(status=Booking.Status.PENDING).count(),
        'returning': awaiting_relocation(scoped_bookings(user).filter(
            return_location=viewing) if viewing else scoped_bookings(user)).count(),
    }


@staff_api
@require_GET
def api_feed(request):
    """
    Polled every few seconds by every dashboard page. Incremental polls (?since=) return every change in
    the staff member's branches so alerts are never missed; the page itself filters rows by city.
    """
    mark_agent_online()
    viewing = view_location(request)
    since = parse_datetime(request.GET.get('since') or '')
    qs = scoped_bookings(request.user)
    status = request.GET.get('status', '')
    if since:
        qs = qs.filter(updated_at__gt=since)
    else:
        if viewing:
            qs = qs.filter(Q(pickup_location=viewing) | Q(return_location=viewing))
        if status in Booking.Status.values:
            qs = qs.filter(status=status)
    bookings = []
    for b in qs.order_by('-updated_at')[:100]:
        item = b.admin_dict()
        # Only payments that arrived since the last poll chime, not later edits to old paid bookings.
        item['just_paid'] = bool(since and b.paid_at and b.paid_at > since)
        bookings.append(item)
    unread = scoped_chats(request.user).aggregate(total=Sum('unread_for_admin'))['total'] or 0
    return JsonResponse({
        'bookings': bookings,
        'stats': _stats(viewing, request.user),
        'unread_chats': unread,
        'city': viewing.slug if viewing else '',
        'server_time': timezone.now().isoformat(),
    })


@staff_api
@require_POST
def api_booking_action(request, ref):
    booking = get_object_or_404(scoped_bookings(request.user), ref=ref)
    try:
        data = json.loads(request.body or b'{}')
    except ValueError:
        data = {}
    action = data.get('action') if isinstance(data, dict) else None
    try:
        if action == 'pickup':
            booking = mark_picked_up(booking, request.user)
        elif action == 'complete':
            booking = mark_returned(booking, request.user)
        elif action == 'cancel':
            booking = cancel_booking(booking, request.user, data.get('reason'))
        elif action == 'mark_paid':
            booking = mark_paid_manually(booking, request.user, data.get('code'))
        elif action == 'relocate' and booking.awaiting_relocation:
            booking, _ = relocate_car(booking, request.user)
        else:
            return JsonResponse({'error': "That action isn't allowed for this booking's status."}, status=400)
    except ActionError as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    return JsonResponse({'booking': booking.admin_dict()})


def _chat_city(conv):
    return {'city': conv.location.name if conv.location_id else '',
            'city_id': conv.location_id or ''}


@staff_api
@require_GET
def api_chats(request):
    mark_agent_online()
    items = []
    for conv in scoped_chats(request.user)[:50]:
        last = conv.messages.order_by('-id').first()
        items.append({
            'id': str(conv.id),
            'name': conv.name,
            'contact': conv.contact,
            **_chat_city(conv),
            'unread': conv.unread_for_admin,
            'preview': (('You: ' if last and last.sender == 'admin' else '') + last.body[:80]) if last else 'No messages yet',
            'time': timezone.localtime(conv.last_message_at).strftime('%d %b, %H:%M'),
        })
    return JsonResponse({'chats': items})


@staff_api
@require_GET
def api_chat_messages(request, cid):
    conv = get_object_or_404(scoped_chats(request.user), pk=cid)
    try:
        after = int(request.GET.get('after', 0))
    except ValueError:
        after = 0
    items = [m.as_dict() for m in conv.messages.filter(id__gt=after)[:200]]
    if conv.unread_for_admin:
        Conversation.objects.filter(pk=conv.pk).update(unread_for_admin=0)
    return JsonResponse({'messages': items, 'name': conv.name, 'contact': conv.contact, **_chat_city(conv)})


@staff_api
@require_POST
def api_chat_reply(request, cid):
    conv = get_object_or_404(scoped_chats(request.user), pk=cid)
    try:
        body = str(json.loads(request.body or b'{}').get('body') or '').strip()[:1000]
    except ValueError:
        body = ''
    if not body:
        return JsonResponse({'error': 'Type a reply first.'}, status=400)
    msg = Message.objects.create(conversation=conv, sender=Message.Sender.ADMIN, body=body)
    Conversation.objects.filter(pk=conv.pk).update(last_message_at=timezone.now(), unread_for_admin=0)
    return JsonResponse({'message': msg.as_dict()}, status=201)


@staff_api
@require_POST
def api_chat_assign(request, cid):
    """Lets the owner pass a chat to the right branch."""
    if staff_location(request.user) is not None:
        return JsonResponse({'error': 'Only the owner can move chats between branches.'}, status=403)
    conv = get_object_or_404(Conversation, pk=cid)
    try:
        city_id = json.loads(request.body or b'{}').get('city_id')
    except ValueError:
        city_id = None
    conv.location = Location.objects.filter(pk=city_id).first() if str(city_id or '').isdigit() else None
    conv.save(update_fields=['location'])
    return JsonResponse(_chat_city(conv))
