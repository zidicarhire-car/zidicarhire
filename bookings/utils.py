import re

from django.core.cache import cache


def normalize_phone(raw):
    """Turns 0712345678 / 712345678 / +254712345678 into 254712345678. Returns None if invalid."""
    digits = re.sub(r'\D', '', str(raw or ''))
    if digits.startswith('0') and len(digits) == 10:
        digits = '254' + digits[1:]
    elif len(digits) == 9 and digits[0] in '71':
        digits = '254' + digits
    return digits if re.fullmatch(r'254[17]\d{8}', digits) else None


def client_ip(request):
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('HTTP_X_REAL_IP') or request.META.get('REMOTE_ADDR', '')


def rate_limited(request, key, limit, window_seconds):
    """Simple per-IP limiter. Returns True when the caller should be blocked."""
    cache_key = f'rl:{key}:{client_ip(request)}'
    cache.add(cache_key, 0, window_seconds)
    try:
        count = cache.incr(cache_key)
    except ValueError:
        cache.set(cache_key, 1, window_seconds)
        count = 1
    return count > limit
