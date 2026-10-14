"""Dashboard cars: list, add, edit, duplicate, hide, delete, and the photo manager."""
import json
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from bookings.models import Booking
from fleet.images import ImageProblem, save_photo
from fleet.models import Car, CarPhoto

from .forms import CarForm
from .models import staff_location
from .views import _ctx, awaiting_relocation, scoped_bookings, scoped_cars, staff_page, view_location

MAX_PHOTOS = 20


def _upcoming_filter():
    """Bookings still to come or under way: paid, out with the customer, or held while paying."""
    today = timezone.localdate()
    cutoff = timezone.now() - timedelta(minutes=settings.BOOKING_HOLD_MINUTES)
    return Q(bookings__return_date__gte=today) & (
        Q(bookings__status__in=(Booking.Status.PAID, Booking.Status.PICKED_UP))
        | Q(bookings__status=Booking.Status.PENDING, bookings__payment_requested_at__gte=cutoff))


@staff_page
def cars(request):
    own = staff_location(request.user)
    viewing = view_location(request)
    if request.method == 'POST':
        form = CarForm(request.POST, staff_location=own)
        if form.is_valid():
            car = form.save()
            messages.success(request, f'{car.name} added to {car.location}. Now add its photos.')
            return redirect(reverse('dashboard:car_edit', args=[car.pk]) + '#photos')
    else:
        form = CarForm(staff_location=own, default_location=viewing)

    car_list = scoped_cars(request.user).prefetch_related('photos').annotate(
        upcoming=Count('bookings', filter=_upcoming_filter(), distinct=True))
    if viewing:
        car_list = car_list.filter(location=viewing)
    returning = {}
    for booking in awaiting_relocation(scoped_bookings(request.user)).order_by('return_date'):
        returning.setdefault(booking.car_id, []).append(booking)
    car_list = list(car_list.order_by('-is_active', 'location__display_order', 'name'))
    for car in car_list:
        car.returning = returning.get(car.pk, [])
    return render(request, 'dashboard/cars.html', _ctx(request, form=form, cars=car_list, nav='cars'))


@staff_page
def car_edit(request, pk):
    car = get_object_or_404(scoped_cars(request.user).prefetch_related('photos'), pk=pk)
    own = staff_location(request.user)
    if request.method == 'POST':
        form = CarForm(request.POST, instance=car, staff_location=own)
        if form.is_valid():
            car = form.save()
            messages.success(request, f'{car.name} saved.')
            return redirect('dashboard:cars')
    else:
        form = CarForm(instance=car, staff_location=own)
    return render(request, 'dashboard/car_edit.html', _ctx(
        request, form=form, car=car, nav='cars', photos=car.photos.all(), max_photos=MAX_PHOTOS,
        max_mb=settings.MAX_UPLOAD_MB,
    ))


@staff_page
@require_POST
def car_toggle(request, pk):
    car = get_object_or_404(scoped_cars(request.user), pk=pk)
    car.is_active = not car.is_active
    car.save(update_fields=['is_active'])
    messages.success(request, f'{car.name} is now {"shown on" if car.is_active else "hidden from"} the website.')
    return redirect('dashboard:cars')


@staff_page
@require_POST
def car_delete(request, pk):
    car = get_object_or_404(scoped_cars(request.user), pk=pk)
    if car.bookings.exists():
        car.is_active = False
        car.save(update_fields=['is_active'])
        messages.info(request, f'{car.name} has bookings, so it was hidden instead of deleted.')
    else:
        car.delete()  # its photos and their files go too
        messages.success(request, f'{car.name} deleted.')
    return redirect('dashboard:cars')


@staff_page
@require_POST
def car_duplicate(request, pk):
    """Copies a car (e.g. the same model for another branch), hidden until it's checked and shown."""
    original = get_object_or_404(scoped_cars(request.user).prefetch_related('photos'), pk=pk)
    fields = {f.name: getattr(original, f.name) for f in Car._meta.concrete_fields
              if f.name not in ('id', 'created_at')}
    fields.update(name=f'{original.name} (copy)'[:120], is_active=False, features=list(original.features or []))
    with transaction.atomic():
        copy = Car.objects.create(**fields)
        for photo in original.photos.all():
            new = CarPhoto(car=copy, width=photo.width, height=photo.height, order=photo.order,
                           is_cover=photo.is_cover)
            for field in ('image', 'thumbnail'):
                source = getattr(photo, field)
                with source.storage.open(source.name, 'rb') as fh:
                    getattr(new, field).save(source.name.rsplit('/', 1)[-1], ContentFile(fh.read()), save=False)
            new.save()
    messages.success(request, 'Copied. This copy is hidden: change the name, branch or price, then show it.')
    return redirect('dashboard:car_edit', pk=copy.pk)


# ---------- Photo manager (JSON, used by photos.js) ----------

def _photo_car(request, pk):
    return get_object_or_404(scoped_cars(request.user), pk=pk)


def _photos_json(car):
    return {'photos': [p.as_dict() for p in car.photos.all()]}


@staff_page
@require_POST
def photo_upload(request, pk):
    car = _photo_car(request, pk)
    upload = request.FILES.get('image')
    if not upload:
        return JsonResponse({'error': 'Choose a photo to upload.'}, status=400)
    if car.photos.count() >= MAX_PHOTOS:
        return JsonResponse({'error': f'A car can have up to {MAX_PHOTOS} photos. Delete one first.'}, status=400)
    try:
        photo = save_photo(car, upload)
    except ImageProblem as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    return JsonResponse({'photo': photo.as_dict(), **_photos_json(car)}, status=201)


@staff_page
@require_POST
def photo_order(request, pk):
    car = _photo_car(request, pk)
    try:
        ids = [int(i) for i in json.loads(request.body or b'{}').get('order', [])]
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({'error': 'Could not read the new order.'}, status=400)
    photos = {p.pk: p for p in car.photos.all()}
    for position, photo_id in enumerate(i for i in ids if i in photos):
        if photos[photo_id].order != position:
            photos[photo_id].order = position
            photos[photo_id].save(update_fields=['order'])
    return JsonResponse(_photos_json(car))


@staff_page
@require_POST
def photo_cover(request, pk, photo_id):
    car = _photo_car(request, pk)
    photo = get_object_or_404(car.photos, pk=photo_id)
    with transaction.atomic():
        car.photos.exclude(pk=photo.pk).update(is_cover=False)
        photo.is_cover = True
        photo.save(update_fields=['is_cover'])
    return JsonResponse(_photos_json(car))


@staff_page
@require_POST
def photo_delete(request, pk, photo_id):
    car = _photo_car(request, pk)
    photo = get_object_or_404(car.photos, pk=photo_id)
    was_cover = photo.is_cover
    photo.delete()
    if was_cover:
        first = car.photos.order_by('order', 'id').first()
        if first:
            first.is_cover = True
            first.save(update_fields=['is_cover'])
    return JsonResponse(_photos_json(car))
