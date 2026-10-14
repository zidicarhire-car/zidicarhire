from django.conf import settings
from django.utils.functional import SimpleLazyObject


def business(request):
    from .models import Location

    return {
        'business': settings.BUSINESS,
        'site_url': settings.SITE_URL,
        # Only queried when a template uses it (the public footer and chat widget).
        'branches': SimpleLazyObject(lambda: list(Location.objects.active())),
    }
