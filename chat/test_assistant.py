"""The chat assistant answers from real data, hands over to a person, and goes quiet once staff reply."""
import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings

from fleet.test_utils import make_car, make_location, make_point

from . import bot
from .models import Conversation, Message
from .services import mark_agent_online


@override_settings(ADMIN_NOTIFY_EMAILS=['owner@example.com'], BOOKING_MIN_FEE=1000,
                   SITE_URL='https://zidicarhire.pythonanywhere.com')
class AssistantTests(TestCase):
    def setUp(self):
        cache.clear()
        self.nairobi = make_location('nairobi')
        self.mombasa = make_location('mombasa')
        make_point(self.mombasa, 'Moi International Airport', fee=1500)
        make_car(self.nairobi, name='Toyota Vitz', price=3500)
        make_car(self.mombasa, name='Nissan X-Trail', price=7000)
        self.conv = Conversation.objects.create(name='Achieng Otieno')

    def send(self, body):
        with mock.patch('chat.views.rate_limited', return_value=False):
            res = self.client.post(f'/chat/{self.conv.id}/send/', json.dumps({'body': body}),
                                   content_type='application/json')
        self.conv.refresh_from_db()
        return res.json()

    def ask_person(self):
        with mock.patch('chat.views.rate_limited', return_value=False):
            res = self.client.post(f'/chat/{self.conv.id}/agent/', '{}', content_type='application/json')
        self.conv.refresh_from_db()
        return res.json()

    def test_topics(self):
        cases = {
            'How much is a car per day?': 'prices', 'bei ya gari ni ngapi': 'prices',
            'How do I pay with M-Pesa?': 'payment', 'What documents do I need?': 'documents',
            'Where can I pick up the car in Mombasa?': 'locations', 'What time do you open?': 'hours',
            'I want to cancel my booking': 'changes', 'Can I talk to a person?': 'agent',
            'Where is my booking ZCH2CF12805?': 'mybooking', 'How do I book?': 'booking', 'Hello': 'greeting',
            'asdfgh qwerty': None,
        }
        for text, topic in cases.items():
            with self.subTest(text=text):
                self.assertEqual(bot.match_topic(text), topic)

    def test_first_reply_greets_and_answers_with_real_prices(self):
        data = self.send('How much are your cars?')
        self.assertEqual(data['message']['sender'], 'visitor')
        reply = data['replies'][0]
        self.assertEqual((reply['sender'], reply['label']), ('bot', 'Automatic reply'))
        self.assertTrue(reply['body'].startswith('Hi Achieng!'))
        self.assertIn('Toyota Vitz: KES 3,500 per day (Nairobi)', reply['body'])
        self.assertIn('KES 1,000', reply['body'])
        self.assertIn('https://zidicarhire.pythonanywhere.com/cars/', reply['body'])
        self.assertIn('New chat from Achieng Otieno', mail.outbox[0].subject)

    def test_city_specific_answers(self):
        self.assertIn('Nissan X-Trail', self.send('prices in Mombasa?')['replies'][0]['body'])
        body = self.send('Can I collect at the airport in Mombasa?')['replies'][0]['body']
        self.assertIn('Moi International Airport (+KES 1,500)', body)

    def test_talk_to_a_person_button_when_nobody_is_online(self):
        self.send('Hi')
        mail.outbox.clear()
        data = self.ask_person()
        self.assertTrue(self.conv.wants_agent)
        self.assertIn("I've let the team know", data['replies'][0]['body'])
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('wants to talk to a person', mail.outbox[0].subject)
        # Asking again doesn't spam the team or the chat.
        self.assertEqual(self.ask_person()['replies'], [])
        self.assertEqual(len(mail.outbox), 1)
        # The assistant stays quiet while a person is coming.
        self.assertEqual(self.send('Hello?')['replies'], [])

    def test_handover_says_someone_is_online(self):
        mark_agent_online()
        body = self.send('I need to speak to a human please')['replies'][0]['body']
        self.assertIn('asked a team member to join', body)
        self.assertTrue(self.conv.wants_agent)

    def test_cancellations_go_to_a_person(self):
        data = self.send('I want to cancel my booking and get a refund')
        self.assertIn('handled by our team', data['replies'][0]['body'])
        self.assertTrue(data['wants_agent'])

    def test_two_unknown_questions_call_a_person(self):
        first = self.send('asdf qwerty')
        self.assertIn("didn't quite get that", first['replies'][0]['body'])
        self.assertFalse(self.conv.wants_agent)
        second = self.send('zxcv blah')
        self.assertIn('Let me get a person', second['replies'][0]['body'])
        self.assertTrue(self.conv.wants_agent)

    def test_quiet_after_staff_reply_and_staff_reply_clears_the_flag(self):
        self.ask_person()
        staff = get_user_model().objects.create_user('desk', password='pw', is_staff=True)
        self.client.force_login(staff)
        feed = self.client.get('/dashboard/api/feed/').json()
        self.assertEqual(feed['waiting_chats'], [{'id': str(self.conv.id), 'name': 'Achieng Otieno'}])
        chats = self.client.get('/dashboard/api/chats/').json()['chats']
        self.assertTrue(chats[0]['wants_agent'])
        self.assertTrue(chats[0]['preview'].startswith('Auto: '))
        self.client.post(f'/dashboard/api/chats/{self.conv.id}/reply/', json.dumps({'body': 'Hi, Mary here.'}),
                         content_type='application/json')
        self.conv.refresh_from_db()
        self.assertFalse(self.conv.wants_agent)
        self.assertEqual(self.client.get('/dashboard/api/feed/').json()['waiting_chats'], [])
        self.client.logout()
        bot_messages = self.conv.messages.filter(sender=Message.Sender.BOT).count()
        self.assertEqual(self.send('How much is the Vitz?')['replies'], [])
        self.assertEqual(self.conv.messages.filter(sender=Message.Sender.BOT).count(), bot_messages)

    def test_visitor_polling_sees_bot_messages_and_flag(self):
        self.ask_person()
        data = self.client.get(f'/chat/{self.conv.id}/messages/').json()
        self.assertTrue(data['wants_agent'])
        self.assertEqual(data['messages'][0]['sender'], 'bot')


class AdminUrlTests(TestCase):
    def test_admin_opens_the_dashboard(self):
        self.assertRedirects(self.client.get('/admin/'), '/dashboard/', fetch_redirect_response=False)
        self.assertRedirects(self.client.get('/admin/cars/?x=1'), '/dashboard/cars/?x=1', fetch_redirect_response=False)
        self.assertEqual(self.client.get('/admin').status_code, 301)          # adds the slash first
        # Not signed in: the dashboard sends you to its sign-in page.
        self.assertRedirects(self.client.get('/admin/', follow=True), '/dashboard/login/?next=/dashboard/')
        self.assertContains(self.client.get('/'), 'href="/admin/"')
        self.assertIn('Disallow: /admin/', self.client.get('/robots.txt').content.decode())
