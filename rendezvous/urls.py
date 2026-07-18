from django.urls import path
from . import views



urlpatterns = [
    path('calendrier/', views.calendrier, name='calendrier'),
    path('', views.historique_paiement, name='historique_paiement'),
    
    # 1. Route pour une nouvelle vente (sans ID)
    path('nouveau/', views.paiement, name='paiement'),
    
    # 2. AJOUTE CETTE LIGNE : Route pour modifier une vente existante (avec UUID)
    path('nouveau/<uuid:groupe_id>/', views.paiement, name='paiement'),
    
    path('rendezvous/<uuid:groupe_id>/', views.paiement_detail, name='paiement_detail'),
    
    # Attention ici : ta vue de suppression utilise-t-elle le PK ou le groupe_id ?
    # On remplace <int:pk> par <uuid:groupe_id>
    path('supprimer/<uuid:groupe_id>/', views.paiement_delete, name='paiement_delete'),


    path('rendezvous/signaler/<uuid:groupe_id>/', views.signaler_paiements, name='signaler_paiement'),




    path('api/pack/<int:pack_id>/details/', views.get_pack_details, name='get_pack_details'),
]