from django.contrib import admin
from .models import Salon, Service, CategorieService, Parametre
from django.contrib import admin
from django.db import models
from django.forms import CheckboxSelectMultiple  # <--- Cet import est crucial

# Register your models here.

@admin.register(Salon)
class SalonAdmin(admin.ModelAdmin):
    list_display = ('nom', 'telephone', 'email')
    fieldsets = (
        ('Informations', {
            'fields': ('nom', 'adresse', 'telephone', 'email', 'horaire_ouverture')
        }),
    )

@admin.register(CategorieService)
class CategorieServiceAdmin(admin.ModelAdmin):
    list_display = ('nom', 'ordre')
    list_editable = ('ordre',)




'''
@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('nom', 'categorie', 'duree', 'prix', 'commission', 'actif')
    list_filter = ('categorie', 'actif')
    search_fields = ('nom', 'description')
    list_editable = ('prix', 'commission', 'actif')
    fieldsets = (
        ('Informations', {
            'fields': ('code', 'nom', 'categorie', 'description')
        }),
        ('Détails', {
            'fields': ('duree', 'prix', 'commission', 'couleur')
        }),
        ('Statut', {
            'fields': ('actif',)
        }),
    )

'''

from django.contrib import admin
from .models import Service, CategorieService, Parametre

@admin.register(Parametre)
class ParametreAdmin(admin.ModelAdmin):
    list_display = ('cle', 'description')
    search_fields = ('cle', 'description')


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('code', 'nom', 'categorie', 'prix', 'est_un_pack', 'actif')
    list_filter = ('categorie', 'actif', 'est_un_pack')
    search_fields = ('nom', 'code')
    
    # ON FORCE LES CASES À COCHER ICI
    formfield_overrides = {
        models.ManyToManyField: {'widget': CheckboxSelectMultiple},
    }

    fieldsets = (
        ('Informations Générales', {
            'fields': ('code', 'nom', 'categorie', 'description', 'couleur'),
        }),
        ('Paramètres de Vente', {
            'fields': ('duree', 'prix', 'actif'),
        }),
        ('Configuration du Pack', {
            'fields': ('est_un_pack', 'services_inclus'),
            'description': "Cochez 'Est un pack' puis cochez les services simples à inclure ci-dessous."
        }),
    )

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        """ Filtre pour ne pas afficher de packs dans la liste des services à cocher """
        if db_field.name == "services_inclus":
            kwargs["queryset"] = Service.objects.filter(est_un_pack=False, actif=True)
        return super().formfield_for_manytomany(db_field, request, **kwargs)