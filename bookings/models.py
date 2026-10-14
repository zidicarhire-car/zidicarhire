import secrets
from datetime import time, timedelta

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


def new_ref():
    return 'ZCH' + secrets.token_hex(4).upper()


class BookingQuerySet(models.QuerySet):
    def with_details(self):
        return self.select_related('car', 'pickup_location', 'pickup_point', 'return_location')

    def blocking(self):
        """
        Bookings that hold a car: paid ones and cars out on hire, plus unpaid ones still inside the
        hold window. Returned (completed) bookings no longer hold the car.
        """
        cutoff = timezone.now() - timedelta(minutes=settings.BOOKING_HOLD_MINUTES)
        return self.filter(
            Q(status__in=(Booking.Status.PAID, Booking.Status.PICKED_UP))
            | Q(status=Booking.Status.PENDING, payment_requested_at__gte=cutoff)
        )


class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Waiting for payment'
        PAID = 'paid', 'Paid'
        PICKED_UP = 'picked_up', 'Picked up'
        COMPLETED = 'completed', 'Returned'
        CANCELLED = 'cancelled', 'Cancelled'
        FAILED = 'failed', 'Payment failed'

    # Statuses where the customer has paid; these get a receipt.
    PAID_STATES = (Status.PAID, Status.PICKED_UP, Status.COMPLETED)

    ref = models.CharField(max_length=12, unique=True, default=new_ref, editable=False)
    car = models.ForeignKey('fleet.Car', on_delete=models.PROTECT, related_name='bookings')
    customer_name = models.CharField(max_length=120)
    phone = models.CharField(max_length=15, help_text='M-Pesa number in 2547XXXXXXXX format')
    email = models.EmailField(blank=True)
    pickup_location = models.ForeignKey('fleet.Location', on_delete=models.PROTECT, null=True,
                                        related_name='pickup_bookings', help_text='Branch the car is collected from')
    pickup_point = models.ForeignKey('fleet.PickupPoint', on_delete=models.PROTECT, null=True, blank=True,
                                     related_name='bookings')
    return_location = models.ForeignKey('fleet.Location', on_delete=models.PROTECT, null=True,
                                        related_name='return_bookings', help_text='Branch the car is returned to')
    notes = models.TextField(blank=True, help_text='Flight number, hotel or delivery address, and older free-text pick-up details')
    pickup_date = models.DateField()
    pickup_time = models.TimeField(default=time(10, 0))
    return_date = models.DateField()
    return_time = models.TimeField(default=time(10, 0))
    days = models.PositiveSmallIntegerField(help_text='Every started 24 hours counts as a day')
    id_number = models.CharField(max_length=20, blank=True, verbose_name='ID or passport number')
    licence_number = models.CharField(max_length=20, blank=True, verbose_name='Driving licence number')
    # Prices as they were when the customer booked, so later price changes don't alter old receipts.
    daily_rate = models.PositiveIntegerField(default=0, help_text='Price per day in KES at the time of booking')
    rate_type = models.CharField(max_length=10, default='daily', help_text='daily, weekly or monthly rate')
    pickup_fee = models.PositiveIntegerField(default=0, help_text='Pick-up point fee in KES')
    one_way_fee = models.PositiveIntegerField(default=0, help_text='One-way return fee in KES')
    extras_amount = models.PositiveIntegerField(default=0, help_text='Extras in KES')
    amount = models.PositiveIntegerField(help_text='Total in KES')
    amount_paid = models.PositiveIntegerField(default=0, help_text='KES received by M-Pesa (or marked paid by staff)')
    car_relocated = models.BooleanField(
        default=False, help_text='For one-way hires: the car has arrived and was moved to the return branch'
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)

    checkout_request_id = models.CharField(max_length=100, blank=True)
    payhero_reference = models.CharField(max_length=100, blank=True)
    mpesa_receipt = models.CharField(max_length=40, blank=True)
    result_desc = models.CharField(max_length=255, blank=True)
    payment_requested_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    objects = BookingQuerySet.as_manager()

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['car', 'pickup_date', 'return_date'])]

    def __str__(self):
        return f'{self.ref} - {self.customer_name}'

    @property
    def masked_phone(self):
        p = self.phone
        return f'0{p[3:6]} *** {p[-3:]}' if len(p) == 12 else p

    @property
    def local_phone(self):
        return f'0{self.phone[3:]}' if len(self.phone) == 12 else self.phone

    @property
    def is_paid(self):
        return self.status in self.PAID_STATES

    @property
    def is_one_way(self):
        return bool(self.return_location_id and self.pickup_location_id
                    and self.return_location_id != self.pickup_location_id)

    @property
    def awaiting_relocation(self):
        """A paid one-way hire whose car the admin hasn't yet moved to the return branch."""
        return self.is_one_way and not self.car_relocated and self.is_paid

    @property
    def whatsapp_link(self):
        return f'https://wa.me/{self.phone}' if len(self.phone) == 12 else ''

    @property
    def balance(self):
        """Positive: the customer still owes this. Negative: we owe them (after a date change)."""
        return self.amount - self.amount_paid if self.is_paid else 0

    @property
    def balance_abs(self):
        return abs(self.balance)

    def price_lines(self):
        from .pricing import price_lines

        return price_lines(
            days=self.days, daily_rate=self.daily_rate or (self.amount // max(self.days, 1)),
            pickup_point=self.pickup_point, pickup_fee=self.pickup_fee,
            return_location=self.return_location if self.is_one_way else None, one_way_fee=self.one_way_fee,
            extras=self.extras_amount, extra_items=[(e.label, e.amount) for e in self.extras.all()],
            rate_type=self.rate_type,
        )

    def public_dict(self):
        return {
            'ref': self.ref,
            'status': self.status,
            'status_label': self.get_status_display(),
            'amount': self.amount,
            'days': self.days,
            'car': self.car.name,
            'pickup_date': self.pickup_date.isoformat(),
            'pickup_time': self.pickup_time.strftime('%H:%M'),
            'return_date': self.return_date.isoformat(),
            'return_time': self.return_time.strftime('%H:%M'),
            'phone': self.masked_phone,
            'receipt': self.mpesa_receipt,
            'message': self.result_desc if self.status == self.Status.FAILED else '',
            'city': self.pickup_location.name if self.pickup_location_id else '',
            'pickup_point': self.pickup_point.name if self.pickup_point_id else '',
            'return_city': self.return_location.name if self.is_one_way else '',
            'breakdown': self.price_lines(),
        }

    def admin_dict(self):
        return {
            **self.public_dict(),
            'customer_name': self.customer_name,
            'phone': self.local_phone,
            'email': self.email,
            'city_slug': self.pickup_location.slug if self.pickup_location_id else '',
            'return_city_slug': self.return_location.slug if self.is_one_way else '',
            'notes': self.notes,
            'awaiting_relocation': self.awaiting_relocation,
            'result_desc': self.result_desc,
            'created': timezone.localtime(self.created_at).strftime('%d %b, %H:%M'),
            'paid_at': timezone.localtime(self.paid_at).strftime('%d %b, %H:%M') if self.paid_at else '',
            'updated_at': self.updated_at.isoformat(),
        }


class BookingEvent(models.Model):
    """One line in a booking's timeline: what happened, who did it and when."""

    class Kind(models.TextChoices):
        CREATED = 'created', 'Booking made'
        PROMPT = 'prompt', 'M-Pesa prompt sent'
        PAID = 'paid', 'Paid'
        FAILED = 'failed', 'Payment failed'
        PICKED_UP = 'picked_up', 'Picked up'
        RETURNED = 'returned', 'Returned'
        CANCELLED = 'cancelled', 'Cancelled'
        DATES = 'dates', 'Dates changed'
        EMAIL = 'email', 'Email sent'
        RELOCATED = 'relocated', 'Car moved branch'
        NOTE = 'note', 'Note'

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='events')
    kind = models.CharField(max_length=12, choices=Kind.choices)
    message = models.TextField(blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                             related_name='+', help_text='Staff member, or empty for the customer or system')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f'{self.booking.ref}: {self.get_kind_display()}'

    @property
    def who(self):
        if self.user_id:
            return self.user.get_full_name() or self.user.get_username()
        return 'Customer' if self.kind in (self.Kind.CREATED, self.Kind.PROMPT) else 'System'


def log_event(booking, kind, message='', user=None):
    return BookingEvent.objects.create(booking=booking, kind=kind, message=message[:2000],
                                       user=user if user is not None and user.is_authenticated else None)


class BookingExtra(models.Model):
    """An extra the customer chose, with its price copied at the time of booking."""
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='extras')
    extra = models.ForeignKey('fleet.Extra', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    name = models.CharField(max_length=80)
    price = models.PositiveIntegerField()
    per_day = models.BooleanField(default=True)
    amount = models.PositiveIntegerField(help_text='Total for this extra in KES')

    class Meta:
        ordering = ['id']

    def __str__(self):
        return self.name

    @property
    def label(self):
        return f'{self.name} (KES {self.price:,}/day)' if self.per_day else self.name
