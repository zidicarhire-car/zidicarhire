from django.db import models


class Payment(models.Model):
    """One M-Pesa prompt sent through PayHero. A booking can have several (e.g. after a retry)."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Waiting for customer'
        SUCCESS = 'success', 'Paid'
        FAILED = 'failed', 'Failed'
        CANCELLED = 'cancelled', 'Cancelled by customer'

    booking = models.ForeignKey('bookings.Booking', on_delete=models.CASCADE, null=True, blank=True,
                                related_name='payments')
    is_test = models.BooleanField(default=False, help_text='A KES 1 test prompt sent from the dashboard')
    requested_by = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    reference = models.CharField(max_length=40, db_index=True, help_text='Our reference sent to PayHero')
    amount = models.PositiveIntegerField(help_text='KES')
    phone = models.CharField(max_length=15)
    payhero_reference = models.CharField(max_length=100, blank=True)
    checkout_request_id = models.CharField(max_length=100, blank=True, db_index=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    mpesa_receipt = models.CharField(max_length=40, blank=True)
    result_code = models.CharField(max_length=20, blank=True)
    result_desc = models.CharField(max_length=255, blank=True)
    raw_callback = models.JSONField(null=True, blank=True, help_text='What PayHero sent to the callback URL')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.reference} KES {self.amount} ({self.get_status_display()})'

    @property
    def masked_phone(self):
        p = self.phone
        return f'0{p[3:6]} *** {p[-3:]}' if len(p) == 12 else p
