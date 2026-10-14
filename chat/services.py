from django.core.cache import cache

AGENT_SEEN_KEY = 'chat:agent-seen'


def mark_agent_online():
    """The dashboard calls this while open, so visitors can see someone is around."""
    cache.set(AGENT_SEEN_KEY, True, 90)


def agent_online():
    return bool(cache.get(AGENT_SEEN_KEY))
