import uuid

from django.db import models
from django.utils import timezone


class Conversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=80)
    contact = models.CharField(max_length=120, blank=True, help_text='Phone or email the visitor gave')
    location = models.ForeignKey('fleet.Location', on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='conversations', help_text='City the visitor is asking about')
    unread_for_admin = models.PositiveIntegerField(default=0)
    last_message_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-last_message_at']

    def __str__(self):
        return self.name


class Message(models.Model):
    class Sender(models.TextChoices):
        VISITOR = 'visitor', 'Visitor'
        ADMIN = 'admin', 'ZIDICARHIRE'

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.CharField(max_length=10, choices=Sender.choices)
    body = models.TextField(max_length=1000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']

    def as_dict(self):
        return {
            'id': self.id,
            'sender': self.sender,
            'body': self.body,
            'time': timezone.localtime(self.created_at).strftime('%H:%M'),
        }
