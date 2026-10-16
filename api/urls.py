"""Mobile app API, version 1. Customer endpoints are public; /staff/ needs "Authorization: Token <key>"."""
from django.urls import path
from django.views.decorators.csrf import csrf_exempt

from bookings.views import quote_view
from chat import views as chat

from . import staff, views

app_name = 'api'

urlpatterns = [
    path('config/', views.config, name='config'),
    path('cars/', views.cars, name='cars'),
    path('cars/<int:pk>/', views.car_detail, name='car'),
    path('quote/', quote_view, name='quote'),
    path('bookings/', views.booking_create, name='booking_create'),
    path('bookings/find/', views.booking_find, name='booking_find'),
    path('bookings/<str:ref>/', views.booking_status, name='booking'),
    path('bookings/<str:ref>/retry/', views.booking_retry, name='booking_retry'),
    # Chat: the conversation's long random id is its key, as on the website.
    path('chat/', csrf_exempt(chat.start), name='chat_start'),
    path('chat/<uuid:cid>/messages/', chat.messages, name='chat_messages'),
    path('chat/<uuid:cid>/send/', csrf_exempt(chat.send), name='chat_send'),
    path('chat/<uuid:cid>/agent/', csrf_exempt(chat.request_agent), name='chat_agent'),

    path('staff/login/', staff.login, name='staff_login'),
    path('staff/logout/', staff.logout, name='staff_logout'),
    path('staff/me/', staff.profile, name='staff_me'),
    path('staff/overview/', staff.overview, name='staff_overview'),
    path('staff/feed/', staff.feed, name='staff_feed'),
    path('staff/bookings/', staff.bookings, name='staff_bookings'),
    path('staff/bookings/<str:ref>/', staff.booking_detail, name='staff_booking'),
    path('staff/bookings/<str:ref>/action/', staff.booking_action, name='staff_booking_action'),
    path('staff/cars/', staff.cars, name='staff_cars'),
    path('staff/cars/<int:pk>/toggle/', staff.car_toggle, name='staff_car_toggle'),
    path('staff/cars/<int:pk>/photos/', staff.photo_upload, name='staff_photo_upload'),
    path('staff/chats/', staff.chats, name='staff_chats'),
    path('staff/chats/<uuid:cid>/messages/', staff.chat_messages, name='staff_chat_messages'),
    path('staff/chats/<uuid:cid>/reply/', staff.chat_reply, name='staff_chat_reply'),
    path('staff/chats/<uuid:cid>/assign/', staff.chat_assign, name='staff_chat_assign'),
]
