from django.urls import path

from . import views

app_name = 'fleet'

urlpatterns = [
    path('', views.home, name='home'),
    path('car-hire/<slug:slug>/', views.city, name='city'),
    path('cars/', views.cars, name='cars'),
    path('cars/<int:pk>/<slug:slug>/', views.car_detail, name='car'),
    path('api/availability/', views.availability, name='availability'),
    path('api/cars/<int:pk>/booked-dates/', views.booked_dates, name='booked_dates'),
    path('sitemap.xml', views.sitemap, name='sitemap'),
    path('robots.txt', views.robots, name='robots'),
]
