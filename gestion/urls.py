from django.urls import path
from . import views

urlpatterns = [
    
    path('<int:service_id>/', views.service_detail, name='service_detail'),
    path('services/', views.services_list, name='services_list'),
    path('services/nouveau/', views.service_create, name='service_create'),
    path('services/<int:pk>/modifier/', views.service_edit, name='service_edit'),
    path('services/<int:pk>/supprimer/', views.service_delete, name='service_delete'),
]