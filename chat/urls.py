from django.urls import path

from . import views

app_name = 'chat'

urlpatterns = [
    path('start/', views.start, name='start'),
    path('<uuid:cid>/messages/', views.messages, name='messages'),
    path('<uuid:cid>/send/', views.send, name='send'),
    path('<uuid:cid>/agent/', views.request_agent, name='agent'),
]
