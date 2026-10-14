from datetime import date, timedelta

from django.utils import timezone


def parse_date(value):
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def search_dates(raw_from, raw_to):
    """Returns sensible (start, end) dates from query values, defaulting to tomorrow + 3 days."""
    today = timezone.localdate()
    start = parse_date(raw_from) or today + timedelta(days=1)
    end = parse_date(raw_to) or start + timedelta(days=3)
    if start < today:
        start = today
    if end <= start:
        end = start + timedelta(days=1)
    return start, end
