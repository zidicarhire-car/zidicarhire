"""
Settings for tools/screenshots.py only: the normal settings, but with a throwaway database and media folder,
simulated M-Pesa payments and no rate limits, so UI checks never touch db.sqlite3, media/ or a real till.
"""
import tempfile
from pathlib import Path

from config.settings import *  # noqa: F401,F403
from config.settings import BUSINESS

UI_TMP = Path(tempfile.gettempdir()) / 'zidicarhire-ui'

DEBUG = True
ALLOWED_HOSTS = ['127.0.0.1', 'localhost']
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': UI_TMP / 'ui.sqlite3'}}
MEDIA_ROOT = UI_TMP / 'media'
FAKE_PAYMENTS = True
CACHES = {'default': {'BACKEND': 'django.core.cache.backends.dummy.DummyCache'}}   # no rate limits
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
ADMIN_NOTIFY_EMAILS = []
BUSINESS = {**BUSINESS, 'whatsapp': BUSINESS.get('whatsapp') or '254700000000'}   # so the WhatsApp buttons show
ROOT_URLCONF = 'tools.ui_urls'   # adds /__ui/404/ and /__ui/500/
