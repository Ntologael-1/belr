from django.urls import path
from . import views

urlpatterns = [
    path('', views.clients_list, name='clients_list'),
    path('nouveau/', views.client_create, name='client_create'),
    #path('<int:service_id>/', views.client_detail, name='client_detail'),
    #path('<int:pk>/modifier/', views.client_edit, name='client_edit'),
    path('historique/ajouter/', views.historique_create, name='historique_create'),
]