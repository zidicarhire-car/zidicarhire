"""Settings come from .env: placeholders count as blank, numbers and times are parsed, defaults are safe."""
import json
import os
import subprocess
import sys
from datetime import time
from pathlib import Path

from django.test import SimpleTestCase

from .env import env_bool, env_int, env_list, env_str, env_time

BASE_DIR = Path(__file__).resolve().parent.parent

PRINT_SETTINGS = """
import json, django
from django.conf import settings
django.setup()
print(json.dumps({
    'DEBUG': settings.DEBUG, 'SECRET_KEY': settings.SECRET_KEY, 'ALLOWED_HOSTS': settings.ALLOWED_HOSTS,
    'PAYHERO_AUTH_TOKEN': settings.PAYHERO_AUTH_TOKEN, 'PAYHERO_CHANNEL_ID': settings.PAYHERO_CHANNEL_ID,
    'FAKE_PAYMENTS': settings.FAKE_PAYMENTS, 'MAX_RENTAL_DAYS': settings.MAX_RENTAL_DAYS,
    'MIN_RENTAL_DAYS': settings.MIN_RENTAL_DAYS, 'OPEN': settings.BUSINESS_OPEN_TIME.isoformat(),
    'CLOSE': settings.BUSINESS_CLOSE_TIME.isoformat(), 'MAX_UPLOAD_MB': settings.MAX_UPLOAD_MB,
    'EMAIL_BACKEND': settings.EMAIL_BACKEND, 'ADMIN_NOTIFY_EMAILS': settings.ADMIN_NOTIFY_EMAILS,
    'BUSINESS': settings.BUSINESS, 'HOLD': settings.BOOKING_HOLD_MINUTES,
}))
"""


def load_settings(**env):
    """Imports config.settings in a fresh Python with these environment values (they win over .env)."""
    full_env = {**os.environ, 'DJANGO_SETTINGS_MODULE': 'config.settings', **env}
    result = subprocess.run([sys.executable, '-c', PRINT_SETTINGS], cwd=BASE_DIR, env=full_env,
                            capture_output=True, text=True, timeout=60)
    return result


class EnvHelperTests(SimpleTestCase):
    def test_placeholders_count_as_blank(self):
        environ = {'A': 'FILL_ME', 'B': 'Basic FILL_ME', 'C': '  real  ', 'D': ''}
        self.assertEqual(env_str('A', 'default', environ), 'default')
        self.assertEqual(env_str('B', '', environ), '')
        self.assertEqual(env_str('C', '', environ), 'real')
        self.assertEqual(env_str('D', 'x', environ), 'x')
        self.assertEqual(env_list('L', '', {'L': 'a@x.com, FILL_ME@gmail.com,,b@x.com'}), ['a@x.com', 'b@x.com'])

    def test_bools_ints_and_times(self):
        self.assertTrue(env_bool('X', False, {'X': 'TRUE'}))
        self.assertFalse(env_bool('X', True, {'X': 'no'}))
        self.assertTrue(env_bool('X', True, {}))
        self.assertEqual(env_int('N', 5, {'N': 'abc'}), 5)
        self.assertEqual(env_int('N', 5, {'N': '0'}, minimum=1), 1)
        self.assertEqual(env_time('T', '07:00', {'T': '06:30'}), time(6, 30))
        self.assertEqual(env_time('T', '07:00', {'T': 'late'}), time(7, 0))


class SettingsLoadingTests(SimpleTestCase):
    def test_values_are_read_from_the_environment(self):
        result = load_settings(
            DEBUG='false', SECRET_KEY='s' * 50, ALLOWED_HOSTS='www.zidicarhire.com, zidicarhire.com',
            PAYHERO_AUTH_TOKEN='Basic FILL_ME', PAYHERO_CHANNEL_ID='4321', FAKE_PAYMENTS='false',
            MIN_RENTAL_DAYS='2', MAX_RENTAL_DAYS='30', BUSINESS_OPEN_TIME='06:30', BUSINESS_CLOSE_TIME='21:00',
            MAX_UPLOAD_MB='8', EMAIL_HOST='smtp.gmail.com', EMAIL_HOST_USER='me@gmail.com',
            EMAIL_HOST_PASSWORD='FILL_ME', ADMIN_NOTIFY_EMAILS='a@x.com,FILL_ME@gmail.com',
            BUSINESS_NAME='ZIDI TEST', KRA_PIN='P0512', MPESA_TILL_NUMBER='123456', BOOKING_HOLD_MINUTES='15',
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        s = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertFalse(s['DEBUG'])
        self.assertEqual(s['ALLOWED_HOSTS'], ['www.zidicarhire.com', 'zidicarhire.com'])
        self.assertEqual(s['PAYHERO_AUTH_TOKEN'], '')            # placeholder ignored
        self.assertEqual(s['PAYHERO_CHANNEL_ID'], '4321')
        self.assertFalse(s['FAKE_PAYMENTS'])
        self.assertEqual((s['MIN_RENTAL_DAYS'], s['MAX_RENTAL_DAYS']), (2, 30))
        self.assertEqual((s['OPEN'], s['CLOSE']), ('06:30:00', '21:00:00'))
        self.assertEqual((s['MAX_UPLOAD_MB'], s['HOLD']), (8, 15))
        self.assertIn('console', s['EMAIL_BACKEND'])             # password still a placeholder
        self.assertEqual(s['ADMIN_NOTIFY_EMAILS'], ['a@x.com'])
        self.assertEqual((s['BUSINESS']['name'], s['BUSINESS']['kra_pin'], s['BUSINESS']['till_number']),
                         ('ZIDI TEST', 'P0512', '123456'))

    def test_live_site_refuses_to_start_without_a_secret_key(self):
        result = load_settings(DEBUG='false', SECRET_KEY='FILL_ME')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Set SECRET_KEY in .env', result.stderr)
