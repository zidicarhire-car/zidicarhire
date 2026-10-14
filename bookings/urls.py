from django.urls import path

from . import views

app_name = 'bookings'

urlpatterns = [
    path('create/', views.create_booking, name='create'),
    path('quote/', views.quote_view, name='quote'),
    path('find/', views.find_booking, name='find'),
    path('<str:ref>/', views.booking_detail, name='detail'),
    path('<str:ref>/status/', views.booking_status, name='status'),
    path('<str:ref>/retry/', views.retry_payment, name='retry'),
    path('<str:ref>/calendar.ics', views.booking_ics, name='ics'),
    path('<str:ref>/receipt.pdf', views.receipt_pdf, name='receipt_pdf'),
    path('<str:ref>/receipt/', views.receipt_page, name='receipt'),
]
