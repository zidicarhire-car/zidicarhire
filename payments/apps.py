import logging

from django.apps import AppConfig
from django.core import checks

logger = logging.getLogger(__name__)


def payhero_settings_check(app_configs, **kwargs):
    """Shows up in `manage.py check` and runserver. A warning, never a crash."""
    from .payhero import config_problems

    return [checks.Warning(problem, hint='See .env.example and README.md.', id='payments.W001')
            for problem in config_problems()]


class PaymentsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'payments'

    def ready(self):
        from .payhero import config_problems

        checks.register(payhero_settings_check, checks.Tags.compatibility)
        for problem in config_problems():
            logger.error('M-Pesa payments are not set up: %s', problem)
