from unittest import mock

from django.core import mail
from django.test import TestCase, override_settings

from fleet.test_utils import make_car, make_location

from .models import ContactMessage


class StaticPagesTests(TestCase):
    def test_pages_render_with_titles_and_owner_notes(self):
        for url, text in (('/about/', 'About'), ('/faq/', 'Questions about car hire'), ('/terms/', 'Terms of hire'),
                          ('/privacy/', 'Privacy policy'), ('/contact/', 'Contact us')):
            with self.subTest(url=url):
                res = self.client.get(url)
                self.assertEqual(res.status_code, 200)
                self.assertContains(res, text)
        self.assertContains(self.client.get('/terms/'), 'Owner to edit')
        self.assertContains(self.client.get('/faq/'), 'Owner to confirm')

    def test_faq_structured_data_only_has_confirmed_answers(self):
        res = self.client.get('/faq/')
        self.assertContains(res, '"@type": "FAQPage"')
        jsonld = res.content.decode().split('application/ld+json">')[1].split('</script>')[0]
        self.assertIn('How do I pay?', jsonld)
        self.assertNotIn('security deposit', jsonld)

    def test_custom_404(self):
        res = self.client.get('/no-such-page/')
        self.assertEqual(res.status_code, 404)
        self.assertContains(res, 'find that page', status_code=404)
        self.assertContains(res, 'Find my booking', status_code=404)


@override_settings(ADMIN_NOTIFY_EMAILS=['owner@example.com'])
class ContactFormTests(TestCase):
    def post(self, **data):
        with mock.patch('pages.views.rate_limited', return_value=False):
            return self.client.post('/contact/', {'name': 'Otieno', 'phone': '0712345678', 'message': 'Do you have a van?',
                                                  **data})

    def test_message_is_saved_and_emailed_to_the_branch(self):
        kisumu = make_location('kisumu', notify_email='kisumu@example.com')
        res = self.post(location=kisumu.pk)
        self.assertRedirects(res, '/contact/')
        msg = ContactMessage.objects.get()
        self.assertEqual(msg.location.slug, 'kisumu')
        self.assertEqual(set(mail.outbox[0].to), {'owner@example.com', 'kisumu@example.com'})
        self.assertIn('Do you have a van?', mail.outbox[0].body)

    def test_needs_a_way_to_reply(self):
        res = self.post(phone='', email='')
        self.assertContains(res, 'Give a phone number or an email address')
        self.assertFalse(ContactMessage.objects.exists())

    def test_spam_bots_are_ignored(self):
        self.post(website='http://spam.example')
        self.assertFalse(ContactMessage.objects.exists())
        self.assertEqual(mail.outbox, [])


class CarListingTests(TestCase):
    def setUp(self):
        nairobi = make_location('nairobi')
        self.vitz = make_car(nairobi, name='Toyota Vitz', price=3000)
        self.vitz.transmission = 'manual'
        self.vitz.save()
        self.prado = make_car(nairobi, name='Land Cruiser Prado', price=12000)
        self.prado.seats = 7
        self.prado.category = '4x4'
        self.prado.save()
        self.axio = make_car(nairobi, name='Toyota Axio', price=4500)

    def names(self, **params):
        res = self.client.get('/cars/', {'city': 'nairobi', **params})
        self.assertEqual(res.status_code, 200)
        return [c.name for c in res.context['cars']]

    def test_filters(self):
        self.assertEqual(self.names(transmission='manual'), ['Toyota Vitz'])
        self.assertEqual(self.names(seats=7), ['Land Cruiser Prado'])
        self.assertEqual(self.names(category='4x4'), ['Land Cruiser Prado'])
        self.assertEqual(self.names(price_min=4000, price_max=5000), ['Toyota Axio'])

    def test_sort(self):
        self.assertEqual(self.names(sort='price_asc'), ['Toyota Vitz', 'Toyota Axio', 'Land Cruiser Prado'])
        self.assertEqual(self.names(sort='price_desc'), ['Land Cruiser Prado', 'Toyota Axio', 'Toyota Vitz'])

    def test_bad_filter_values_are_ignored(self):
        self.assertEqual(len(self.names(seats='lots', price_min='abc', sort='random', transmission='x')), 3)

    def test_partial_returns_results_only_and_no_match_message(self):
        res = self.client.get('/cars/', {'city': 'nairobi', 'price_max': 100, 'partial': 1})
        self.assertNotContains(res, '<html')
        self.assertContains(res, 'No cars match these filters')
        self.assertContains(res, '0 of 3 cars match your filters')

    def test_home_shows_featured_cars_why_faq_and_seo(self):
        res = self.client.get('/', {'city': 'nairobi'})
        for text in ('Why book with us', 'How do I pay?', 'Need a car this week?', 'og:image', 'og:title',
                     'rel="apple-touch-icon"', 'zidicarhire-logo-white.svg', 'alt="ZidiCarHire"'):
            self.assertContains(res, text)
        self.assertEqual(len(res.context['featured']), 3)
