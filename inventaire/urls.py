from django.urls import path
from . import views

app_name = 'inventaire'

urlpatterns = [
    path('', views.liste_produits, name='liste_produits'),
    path('alertes/', views.liste_produits_bi, name='liste_produit_bi'),
    path('mouvements/', views.historique_mouvements, name='liste_charges'),
    path('produit/<int:produit_id>/', views.detail_produit_bi, name='detail_produit'),
    path('produit/<int:produit_id>/mouvement/', views.ajouter_mouvement_pamp, name='ajouter_mouvement'),
    path('mouvement/<int:mouvement_id>/modifier/', views.ajouter_mouvement_pamp, name='modifier_mouvement'),
    path('produit/nouveau/', views.creer_produit, name='creer_produit'),
    path('produit/<int:pk>/modifier/', views.creer_produit, name='modifier_produit'),
    path('charges/nouvelle/', views.creer_charge, name='creer_charge'),
    #path('charge/modifier/<int:pk>/', views.modifier_charge, name='modifier_charge'),
    path('charge/modifier/<int:pk>/', views.creer_charge, name='modifier_charge'),

    path('historique-global/', views.historique_mouvements_global, name='historique_mouvements_global'),
    
    path('charge/supprimer/<int:pk>/', views.supprimer_charge, name='supprimer_charge'),
    path('charge/<int:charge_id>/paiement/<int:paiement_id>/', views.enregistrer_paiement, name='modifier_paiement'),
    #path('paiement/modifier/<int:pk>/', views.modifier_paiement, name='modifier_paiement'),
    path('paiement/supprimer/<int:pk>/', views.supprimer_paiement, name='supprimer_paiement'),
    path('charges/payer/<int:charge_id>/', views.enregistrer_paiement, name='enregistrer_paiement'),
]
