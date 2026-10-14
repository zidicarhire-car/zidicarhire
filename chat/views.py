import json

from django.db.models import F
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from bookings.notifications import notify_new_chat
from bookings.utils import rate_limited
from fleet.models import Location

from .models import Conversation, Message
from .services import agent_online


def _json(request):
    try:
        return json.loads(request.body or b'{}')
    except ValueError:
        return {}


@require_POST
def start(request):
    if rate_limited(request, 'chat-start', limit=5, window_seconds=3600):
        return JsonResponse({'error': 'Too many chats started. Try again later.'}, status=429)
    data = _json(request)
    name = str(data.get('name') or '').strip()[:80]
    if len(name) < 2:
        return JsonResponse({'error': 'Enter your name to start chatting.'}, status=400)
    contact = str(data.get('contact') or '').strip()[:120]
    city = str(data.get('city') or '').strip()
    location = Location.objects.active().filter(slug=city).first() if city else None
    conversation = Conversation.objects.create(name=name, contact=contact, location=location)
    return JsonResponse({'id': str(conversation.id), 'name': conversation.name}, status=201)


@require_GET
def messages(request, cid):
    conversation = get_object_or_404(Conversation, pk=cid)
    try:
        after = int(request.GET.get('after', 0))
    except ValueError:
        after = 0
    items = conversation.messages.filter(id__gt=after)[:100]
    return JsonResponse({'messages': [m.as_dict() for m in items], 'agent_online': agent_online()})


@require_POST
def send(request, cid):
    if rate_limited(request, f'chat-send:{cid}', limit=20, window_seconds=60):
        return JsonResponse({'error': "You're sending messages too fast. Wait a moment."}, status=429)
    conversation = get_object_or_404(Conversation.objects.select_related('location'), pk=cid)
    body = str(_json(request).get('body') or '').strip()[:1000]
    if not body:
        return JsonResponse({'error': 'Type a message first.'}, status=400)

    is_first = not conversation.messages.exists()
    message = Message.objects.create(conversation=conversation, sender=Message.Sender.VISITOR, body=body)
    Conversation.objects.filter(pk=conversation.pk).update(
        unread_for_admin=F('unread_for_admin') + 1, last_message_at=timezone.now()
    )
    if is_first:
        notify_new_chat(conversation, body)
    return JsonResponse({'message': message.as_dict()}, status=201)
