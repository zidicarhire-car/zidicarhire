from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.shortcuts import redirect
from django.urls import include, path

admin.site.site_header = 'ZIDICARHIRE admin'


def to_dashboard(request, rest=''):
    """/admin/ and anything under it opens the staff dashboard (sign-in first if needed)."""
    query = request.META.get('QUERY_STRING', '')
    return redirect('/dashboard/' + rest + (f'?{query}' if query else ''))


urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('api/v1/', include('api.urls')),
    path('dashboard/', include('dashboard.urls')),
    path('admin/', to_dashboard),
    path('admin/<path:rest>', to_dashboard),
    path('bookings/', include('bookings.urls')),
    path('payments/', include('payments.urls')),
    path('chat/', include('chat.urls')),
    path('', include('pages.urls')),
    path('', include('fleet.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
