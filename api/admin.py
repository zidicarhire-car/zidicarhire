from django.contrib import admin

from .models import ApiToken


@admin.register(ApiToken)
class ApiTokenAdmin(admin.ModelAdmin):
    """Delete a row to sign that phone out of the staff app."""
    list_display = ('user', 'device', 'created_at', 'last_used_at')
    readonly_fields = ('user', 'device', 'created_at', 'last_used_at')

    def has_add_permission(self, request):
        return False
