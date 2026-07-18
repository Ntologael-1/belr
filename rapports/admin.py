from django.contrib import admin

# Register your models here.

# rapports/admin.py
from django.contrib import admin
from .models import RapportMensuelConsolide

@admin.register(RapportMensuelConsolide)
class RapportMensuelConsolideAdmin(admin.ModelAdmin):
    # Colonnes affichées dans la liste
    list_display = ('get_format_mois', 'annee', 'chiffre_affaires', 'couts_generaux', 'get_effet_ciseau_badge')
    # Filtre latéral par année
    list_filter = ('annee',)
    # Tri par défaut (du plus récent au plus ancien)
    ordering = ('-annee', '-mois')
    
    # Configuration du formulaire de saisie
    fieldsets = (
        ('Période', {
            'fields': ('annee', 'mois')
        }),
        ('Indicateurs Financiers Réels', {
            'fields': ('chiffre_affaires', 'couts_generaux'),
            'description': 'Saisissez les données consolidées réelles de l\'institut pour ce mois.'
        }),
        ('Volumes', {
            'fields': ('nombre_fiches_traitees',),
            'classes': ('collapse',), # Section masquée par défaut pour épurer
        }),
    )

    def get_format_mois(self, obj):
        noms_mois = [
            "Janvier", "Février", "Mars", "Avril", "Mai", "Juin", 
            "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"
        ]
        return noms_mois[obj.mois - 1]
    get_format_mois.short_description = 'Mois'

    def get_effet_ciseau_badge(self, obj):
        eff = obj.effet_ciseau
        if eff > 0:
            return f"🟢 Favorable (+{eff}%)"
        elif eff < 0:
            return f"🔴 Défavorable ({eff}%)"
        return f"⚪ Neutre (0.00%)"
    get_effet_ciseau_badge.short_description = 'Effet Ciseau'
