import hashlib
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

UNUSED_DAYS = 60   # a token nobody has used for this long stops working


def _hash(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


class ApiToken(models.Model):
    """A staff member signed in to the mobile app. Only a hash of the token is stored."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='api_tokens')
    key_hash = models.CharField(max_length=64, unique=True, editable=False)
    device = models.CharField(max_length=120, blank=True, help_text='The phone it was issued to')
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-last_used_at']
        verbose_name = 'app sign-in'

    def __str__(self):
        return f'{self.user} on {self.device or "a phone"}'

    @classmethod
    def issue(cls, user, device=''):
        """Returns (token, raw key). The raw key is shown once, to the app, and never stored."""
        raw = secrets.token_urlsafe(32)
        return cls.objects.create(user=user, key_hash=_hash(raw), device=device[:120]), raw

    @classmethod
    def find(cls, raw):
        """The live token for a raw key, or None (unknown, expired, or the user lost staff access)."""
        if not raw:
            return None
        token = cls.objects.select_related('user').filter(key_hash=_hash(raw)).first()
        if token is None:
            return None
        now = timezone.now()
        if token.last_used_at < now - timedelta(days=UNUSED_DAYS) or not (token.user.is_active and token.user.is_staff):
            token.delete()
            return None
        if token.last_used_at < now - timedelta(minutes=5):   # don't write on every request
            cls.objects.filter(pk=token.pk).update(last_used_at=now)
        return token
