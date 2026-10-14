from django.contrib.auth import views as auth_views
from django.urls import path

from . import booking_views, car_views, settings_check, styleguide, views

app_name = 'dashboard'

urlpatterns = [
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('', booking_views.overview, name='home'),
    path('city/', views.set_city, name='set_city'),
    path('bookings/', booking_views.bookings_list, name='bookings'),
    path('bookings/<str:ref>/', booking_views.booking_detail, name='booking_detail'),
    path('bookings/<str:ref>/receipt.pdf', booking_views.booking_receipt, name='booking_receipt'),
    path('bookings/<str:ref>/relocate/', views.booking_relocate, name='booking_relocate'),
    path('calendar/', booking_views.calendar, name='calendar'),
    path('cars/', car_views.cars, name='cars'),
    path('cars/<int:pk>/edit/', car_views.car_edit, name='car_edit'),
    path('cars/<int:pk>/toggle/', car_views.car_toggle, name='car_toggle'),
    path('cars/<int:pk>/delete/', car_views.car_delete, name='car_delete'),
    path('cars/<int:pk>/duplicate/', car_views.car_duplicate, name='car_duplicate'),
    path('cars/<int:pk>/photos/', car_views.photo_upload, name='photo_upload'),
    path('cars/<int:pk>/photos/order/', car_views.photo_order, name='photo_order'),
    path('cars/<int:pk>/photos/<int:photo_id>/cover/', car_views.photo_cover, name='photo_cover'),
    path('cars/<int:pk>/photos/<int:photo_id>/delete/', car_views.photo_delete, name='photo_delete'),
    path('chats/', views.chats, name='chats'),
    path('reports/', views.reports, name='reports'),
    path('branches/', views.locations, name='locations'),
    path('branches/<int:pk>/', views.location_edit, name='location_edit'),
    path('branches/<int:pk>/toggle/', views.location_toggle, name='location_toggle'),
    path('routes/', views.routes, name='routes'),
    path('settings-check/', settings_check.settings_check, name='settings_check'),
    path('styleguide/', styleguide.styleguide, name='styleguide'),
    path('api/feed/', views.api_feed, name='api_feed'),
    path('api/bookings/<str:ref>/action/', views.api_booking_action, name='api_booking_action'),
    path('api/chats/', views.api_chats, name='api_chats'),
    path('api/chats/<uuid:cid>/messages/', views.api_chat_messages, name='api_chat_messages'),
    path('api/chats/<uuid:cid>/reply/', views.api_chat_reply, name='api_chat_reply'),
    path('api/chats/<uuid:cid>/assign/', views.api_chat_assign, name='api_chat_assign'),
]
