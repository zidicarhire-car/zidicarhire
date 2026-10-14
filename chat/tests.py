import json
from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings

from fleet.test_utils import make_location

from .models import Conversation


@override_settings(ADMIN_NOTIFY_EMAILS=['owner@example.com'])
class ChatCityTests(TestCase):
    def start(self, **data):
        with mock.patch('chat.views.rate_limited', return_value=False):
            res = self.client.post('/chat/start/', json.dumps({'name': 'Otieno', **data}),
                                   content_type='application/json')
        return Conversation.objects.get(pk=res.json()['id'])

    def test_visitor_can_pick_a_city(self):
        kisumu = make_location('kisumu', notify_email='kisumu@example.com')
        conv = self.start(city='kisumu')
        self.assertEqual(conv.location, kisumu)
        with mock.patch('chat.views.rate_limited', return_value=False):
            self.client.post(f'/chat/{conv.id}/send/', json.dumps({'body': 'Need a car'}),
                             content_type='application/json')
        self.assertEqual(set(mail.outbox[0].to), {'owner@example.com', 'kisumu@example.com'})
        self.assertIn('(Kisumu)', mail.outbox[0].subject)

    def test_city_is_optional_and_unknown_cities_are_ignored(self):
        self.assertIsNone(self.start().location)
        self.assertIsNone(self.start(city='atlantis').location)
