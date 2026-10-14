"""
Reads settings from environment variables (loaded from .env by settings.py).

Any value that still contains the FILL_ME placeholder from .env.example counts as not set,
so a half-filled .env never sends "Basic FILL_ME" to PayHero or emails to FILL_ME@gmail.com.
"""
import os
from datetime import time

PLACEHOLDER = 'FILL_ME'


def is_set(value):
    return bool(value and value.strip() and PLACEHOLDER not in value)


def env_str(name, default='', environ=None):
    value = (environ if environ is not None else os.environ).get(name)
    return value.strip() if is_set(value) else default


def env_bool(name, default=False, environ=None):
    value = env_str(name, '', environ)
    if not value:
        return default
    return value.lower() in ('1', 'true', 'yes', 'on')


def env_int(name, default, environ=None, minimum=None):
    try:
        value = int(env_str(name, '', environ))
    except ValueError:
        return default
    return max(value, minimum) if minimum is not None else value


def env_list(name, default='', environ=None):
    """Comma-separated values. Placeholder items are dropped one by one, keeping the real ones."""
    raw = (environ if environ is not None else os.environ).get(name)
    if raw is None or not raw.strip():
        raw = default
    return [item.strip() for item in raw.split(',') if is_set(item)]


def env_time(name, default, environ=None):
    """'07:00' -> time(7, 0). Falls back to `default` (a 'HH:MM' string) if blank or invalid."""
    for raw in (env_str(name, '', environ), default):
        try:
            hours, minutes = (int(part) for part in raw.split(':'))
            return time(hours, minutes)
        except (ValueError, TypeError):
            continue
    return time(0, 0)
