from django.contrib import admin

from payments.models import Payment

from .models import Booking, BookingExtra


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    can_delete = False
    fields = ('created_at', 'amount', 'phone', 'status', 'mpesa_receipt', 'result_code', 'result_desc',
              'checkout_request_id', 'payhero_reference', 'raw_callback')
    readonly_fields = fields
    verbose_name_plural = 'M-Pesa payment attempts'

    def has_add_permission(self, request, obj=None):
        return False


class BookingExtraInline(admin.TabularInline):
    model = BookingExtra
    extra = 0
    readonly_fields = ('extra', 'name', 'price', 'per_day', 'amount')


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('ref', 'customer_name', 'car', 'pickup_location', 'return_location', 'pickup_date', 'return_date',
                    'amount', 'status', 'mpesa_receipt')
    list_filter = ('status', 'pickup_location', 'return_location', 'car')
    search_fields = ('ref', 'customer_name', 'phone', 'email', 'mpesa_receipt')
    inlines = [BookingExtraInline, PaymentInline]
    readonly_fields = ('ref', 'checkout_request_id', 'payhero_reference', 'created_at', 'updated_at', 'paid_at')
