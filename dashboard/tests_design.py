"""Design system: colours meet WCAG AA in light and dark mode, the CSS is split as planned, and the style guide is staff-only."""
import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .styleguide import CONTRAST_PAIRS, contrast, contrast_report, read_tokens

CSS = Path(settings.BASE_DIR) / 'static' / 'css'
HEX = re.compile(r'#[0-9A-Fa-f]{6}')


class ContrastTests(SimpleTestCase):
    def test_contrast_maths(self):
        self.assertAlmostEqual(contrast('#000000', '#FFFFFF'), 21, places=1)
        self.assertAlmostEqual(contrast('#FFFFFF', '#FFFFFF'), 1, places=2)
        # The brand green is too light for white button text, which is why --mpesa-fill exists.
        self.assertLess(contrast('#FFFFFF', '#2E9E3E'), 4.5)

    def test_every_pair_passes_in_light_and_dark(self):
        failures = [f"{r['label']} ({r['fg']} on {r['bg']}): light {r['light']}, dark {r['dark']}, needs {r['min']}"
                    for r in contrast_report() if not (r['light_ok'] and r['dark_ok'])]
        self.assertEqual(failures, [])

    def test_brand_colours_are_exact(self):
        light = read_tokens()['light']
        self.assertEqual(light['--brand'].upper(), '#1C2340')
        self.assertEqual(light['--plate'].upper(), '#F6C21C')
        self.assertEqual(light['--plate-ink'].upper(), '#000000')
        self.assertEqual(light['--mpesa'].upper(), '#2E9E3E')

    def test_pairs_only_use_defined_hex_tokens(self):
        tokens = read_tokens()
        for fg, bg, _minimum, _label in CONTRAST_PAIRS:
            for mode in ('light', 'dark'):
                for name in (fg, bg):
                    self.assertRegex(tokens[mode].get(name, ''), HEX, f'{name} in {mode} mode')


class StylesheetTests(SimpleTestCase):
    def test_css_is_split_into_layers(self):
        for name in ('theme.css', 'site.css', 'dashboard.css'):
            self.assertTrue((CSS / name).exists(), name)
        for gone in ('tokens.css', 'base.css', 'components.css'):
            self.assertFalse((CSS / gone).exists(), f'{gone} should have moved into theme.css')

    def test_colours_live_in_tokens(self):
        """Apart from a few documented exceptions (WhatsApp brand, photo overlays, print), no hex colours outside theme.css."""
        allowed = {'#FFFFFF', '#000000', '#1C2340', '#0B6B35', '#EAF7EF', '#5BD46A', '#FF8A80'}
        for name in ('site.css', 'dashboard.css'):
            found = {h.upper() for h in HEX.findall((CSS / name).read_text(encoding='utf-8'))}
            self.assertEqual(found - allowed, set(), name)

    def test_tokens_have_a_dark_mode_and_reduced_motion(self):
        css = (CSS / 'theme.css').read_text(encoding='utf-8')
        self.assertIn('[data-bs-theme="dark"] {', css)
        self.assertIn('--bs-primary: #1C2340;', css)
        for utility in ('.btn-plate', '.text-plate', '.bg-plate', '.plate {'):
            self.assertIn(utility, css)
        self.assertIn('@media (prefers-reduced-motion: reduce)', css)
        for scale in ('--space-1', '--space-9', '--radius-sm', '--radius-lg', '--shadow-1', '--shadow-2', '--dur', '--ease',
                      '--fs-display', '--fs-h1', '--fs-h2', '--fs-h3', '--fs-body', '--fs-small'):
            self.assertIn(f'{scale}:', css)

    def test_pages_load_the_layers_in_order(self):
        base = (Path(settings.BASE_DIR) / 'templates' / 'base.html').read_text(encoding='utf-8')
        head = (Path(settings.BASE_DIR) / 'templates' / '_theme_head.html').read_text(encoding='utf-8')
        order = [head.index(n) for n in ('data-bs-theme', 'bootstrap@5.3.3/dist/css/bootstrap.min.css',
                                         'bootstrap-icons@1.11.3', 'css/theme.css')]
        self.assertEqual(order, sorted(order), 'theme script first, then Bootstrap, icons, theme.css')
        self.assertLess(base.index('_theme_head.html'), base.index('css/site.css'))
        for tag in re.findall(r'<(?:link|script)[^>]+cdn\.jsdelivr\.net/npm/[^>]+>', head):
            self.assertIn('integrity="sha384-', tag)
            self.assertIn('crossorigin="anonymous"', tag)
        self.assertIn('<script defer src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"', head)
        for template in ('dashboard/base.html', 'dashboard/login.html', '500.html'):
            text = (Path(settings.BASE_DIR) / 'templates' / template).read_text(encoding='utf-8')
            self.assertIn('_theme_head.html', text, template)


class StyleguidePageTests(TestCase):
    def test_staff_only(self):
        url = reverse('dashboard:styleguide')
        self.assertRedirects(self.client.get(url), f"{reverse('dashboard:login')}?next={url}", fetch_redirect_response=False)
        get_user_model().objects.create_user('visitor', password='pw')
        self.client.login(username='visitor', password='pw')
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_shows_tokens_components_and_contrast(self):
        get_user_model().objects.create_user('staff', password='pw', is_staff=True)
        self.client.login(username='staff', password='pw')
        res = self.client.get(reverse('dashboard:styleguide'))
        self.assertEqual(res.status_code, 200)
        for text in ('--brand', '--plate', '--mpesa-fill', 'btn-mpesa', 'btn-plate', 'aria-busy="true"', 'offcanvas-bottom',
                     'data-bs-toggle="modal"', 'role="tablist"', 'data-bs-toggle="tab"', 'status-picked_up', 'alert-danger',
                     'accordion-button', 'sk-line', 'class="empty"', 'data-theme-toggle', 'Pass'):
            self.assertContains(res, text)
        self.assertNotContains(res, 'Fail</span>')
