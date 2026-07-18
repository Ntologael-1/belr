from django.contrib import admin

# Register your models here.from django.contrib import admin
from .models import Client, HistoriqueVisite

@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('nom_complet', 'telephone', 'email', 'date_premiere_visite', 'date_derniere_visite')
    list_filter = ('genre', 'ville')
    search_fields = ('nom', 'prenom', 'telephone', 'email', 'code')
    readonly_fields = ('code', 'date_premiere_visite', 'points_fidelite')
    fieldsets = (
        ('Informations personnelles', {
            'fields': ('code', 'nom', 'prenom', 'genre', 'date_naissance')
        }),
        ('Coordonnées', {
            'fields': ('telephone', 'email', 'adresse', 'ville', 'code_postal')
        }),
        ('Informations salon', {
            'fields': ('date_premiere_visite', 'date_derniere_visite', 'allergies', 'preferences', 'notes')
        }),
        ('Fidélité', {
            'fields': ('points_fidelite', 'parrain')
        }),
    )

@admin.register(HistoriqueVisite)
class HistoriqueVisiteAdmin(admin.ModelAdmin):
    list_display = ('client', 'date_visite', 'employe', 'service', 'montant', 'satisfaction')
    list_filter = ('date_visite', 'employe', 'service')
    search_fields = ('client__nom', 'client__prenom')
    date_hierarchy = 'date_visite'
