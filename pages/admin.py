from django.contrib import admin

from .models import ContactMessage


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'email', 'location', 'created_at', 'handled')
    list_filter = ('handled', 'location')
    list_editable = ('handled',)
    search_fields = ('name', 'phone', 'email', 'message')
    readonly_fields = ('name', 'phone', 'email', 'location', 'message', 'created_at')
