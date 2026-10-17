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


ANDROID = 'Mozilla/5.0 (Linux; Android 14; SM-A155F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Mobile Safari/537.36'
WINDOWS = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36'
IPHONE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile Safari/604.1'
APK, EXE = 'https://example.com/ZidiCarHire.apk', 'https://example.com/ZidiCarHire-Setup.exe'


@override_settings(APP_ANDROID_URL=APK, APP_WINDOWS_URL=EXE)
class GetTheAppTests(TestCase):
    def home(self, ua, **cookies):
        for k, v in cookies.items():
            self.client.cookies[k] = v
        return self.client.get('/', HTTP_USER_AGENT=ua)

    def test_strip_matches_the_visitors_device(self):
        self.assertContains(self.home(ANDROID), 'For Android.')
        self.assertContains(self.home(WINDOWS), 'For Windows.')
        self.assertNotContains(self.home(IPHONE), 'id="app-strip"')

    def test_strip_stays_hidden_once_closed_or_inside_the_desktop_app(self):
        self.assertNotContains(self.home(ANDROID, app_strip='off'), 'id="app-strip"')
        self.assertNotContains(self.home(WINDOWS + ' ZidiCarHireDesktop/1.0.0'), 'id="app-strip"')

    @override_settings(APP_ANDROID_URL='', APP_WINDOWS_URL='')
    def test_nothing_is_offered_without_download_links(self):
        res = self.home(ANDROID)
        self.assertNotContains(res, 'id="app-strip"')
        self.assertNotContains(res, 'Get the app')
        self.assertContains(self.client.get('/app/'), 'Coming soon')

    def test_app_page_has_both_downloads_and_no_strip(self):
        res = self.client.get('/app/', HTTP_USER_AGENT=ANDROID)
        self.assertContains(res, f'href="{APK}"')
        self.assertContains(res, f'href="{EXE}"')
        self.assertContains(res, 'install unknown apps')
        self.assertNotContains(res, 'id="app-strip"')


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
        for text in ('Car hire across Kenya.', 'Why book with us', 'Instant confirmation', 'Our branches',
                     'How it works', 'Is there a security deposit?', 'Owner to confirm', 'Ready when you are.',
                     'og:image', 'og:title', 'rel="apple-touch-icon"', 'zidicarhire-logo-white.svg', 'alt="ZidiCarHire"'):
            self.assertContains(res, text)
        self.assertEqual(len(res.context['featured']), 3)
