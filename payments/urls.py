from django.urls import path

from . import views

app_name = 'payments'

urlpatterns = [
    path('callback/', views.payhero_callback, name='callback'),
]
