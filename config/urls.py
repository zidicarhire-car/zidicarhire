from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = 'ZIDICARHIRE admin'

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('dashboard/', include('dashboard.urls')),
    path('bookings/', include('bookings.urls')),
    path('payments/', include('payments.urls')),
    path('chat/', include('chat.urls')),
    path('', include('pages.urls')),
    path('', include('fleet.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
