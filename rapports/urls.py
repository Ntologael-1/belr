from django.urls import path
from . import views

app_name = 'rapports'

urlpatterns = [
    # Rapport global
    path(
        '',
        views.rapport_global,
        name='rapport_global'
    ),

    # dashboard_bi
    path(
        'bi/',
        views.dashboard_bi_couts,
        name='dashboard_bi'
    ),

    # Rapport détaillé par coiffeur / employé
    path(
        'coiffeur/<int:employe_id>/',
        views.rapport_coiffeur_detail,
        name='rapport_coiffeur_detail'
    ),

    path('rapport-annuel/', views.rapport_annuel_view, name='rapport_annuel'),
]
