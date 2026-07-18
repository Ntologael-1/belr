from django.urls import path
from . import views

urlpatterns = [
    path('', views.employes_list, name='employes_list'),
    path('nouveau/', views.employe_create, name='employe_create'),
    path('<int:pk>/', views.employe_detail, name='employe_detail'),
    path('<int:pk>/modifier/', views.employe_edit, name='employe_edit'),
    path('mon-tableau/', views.tableau_bord_coiffeur, name='tableau_bord_coiffeur'),
    path('toggle/<int:pk>/', views.toggle_employe_status, name='toggle_employe_status'),
    path('employe/<int:pk>/reset-password/', views.reinitialiser_mot_de_passe_employe, name='reinitialiser_mot_de_passe_employe'),
    
    # Route publique pour l'employé (à placer hors des restrictions d'accès)
    path('activation/<uidb64>/<token>/', views.definir_mot_de_passe, name='definir_mot_de_passe'),
    path('employes/<int:pk>/regenerer-lien/', views.regenerer_lien_activation, name='regenerer_lien_activation'),
]