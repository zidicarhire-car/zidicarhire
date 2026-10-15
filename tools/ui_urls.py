"""URLs for tools/screenshots.py: the site's own, plus the real 404 and 500 pages (DEBUG shows its own pages instead)."""
from django.urls import path
from django.views.defaults import page_not_found, server_error

from config.urls import urlpatterns as site_urls

urlpatterns = [
    path('__ui/404/', lambda request: page_not_found(request, None)),
    path('__ui/500/', server_error),
    *site_urls,
]
