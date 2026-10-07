from django.contrib import admin
from django.urls import path,include
from clinic import views
urlpatterns=[
 path('admin/',admin.site.urls),path('accounts/',include('django.contrib.auth.urls')),
 path('',views.home,name='home'),path('health/',views.health,name='health'),
 path('calendar/',views.calendar,name='calendar'),
 path('reports/',views.reports,name='reports'),path('availability/',views.availability,name='availability'),
 path('pets/<int:pk>/history/',views.history,name='history'),
 path('exams/<int:pk>/attachment/',views.attachment,name='attachment'),
 path('invoices/<int:pk>/pdf/',views.invoice_pdf,name='invoice_pdf'),
 path('manage/<str:key>/',views.listing,name='listing'),path('manage/<str:key>/new/',views.edit,name='create'),
 path('manage/<str:key>/<int:pk>/edit/',views.edit,name='edit'),
 path('manage/<str:key>/<int:pk>/<str:operation>/',views.action,name='action'),
]
