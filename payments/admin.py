from django.contrib import admin

from .models import Payment


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('reference', 'amount', 'phone', 'status', 'mpesa_receipt', 'result_code', 'is_test', 'created_at')
    list_filter = ('status', 'is_test')
    search_fields = ('reference', 'phone', 'mpesa_receipt', 'checkout_request_id', 'payhero_reference')
    readonly_fields = [f.name for f in Payment._meta.fields]

    def has_add_permission(self, request):
        return False
