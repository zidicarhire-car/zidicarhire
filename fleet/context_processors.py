from django.conf import settings
from django.utils.functional import SimpleLazyObject


APP_STRIP_COOKIE = 'app_strip'


def app_offer(request):
    """Which app to suggest to this visitor: 'android', 'windows' or '' (none, or they closed the strip)."""
    ua = request.META.get('HTTP_USER_AGENT', '')
    if request.COOKIES.get(APP_STRIP_COOKIE) == 'off' or 'ZidiCarHire' in ua:   # closed it, or already in our app
        return ''
    if 'Android' in ua:
        return 'android' if settings.APP_ANDROID_URL else ''
    if 'Windows' in ua and 'Mobile' not in ua:
        return 'windows' if settings.APP_WINDOWS_URL else ''
    return ''


def business(request):
    from .models import Location

    return {
        'business': settings.BUSINESS,
        'site_url': settings.SITE_URL,
        'apps': {'android': settings.APP_ANDROID_URL, 'windows': settings.APP_WINDOWS_URL},
        'app_offer': app_offer(request),
        # Only queried when a template uses it (the public footer and chat widget).
        'branches': SimpleLazyObject(lambda: list(Location.objects.active())),
    }
