from django.contrib import admin

from .models import Conversation, Message


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('name', 'contact', 'location', 'unread_for_admin', 'last_message_at')
    list_filter = ('location',)
    inlines = [MessageInline]
