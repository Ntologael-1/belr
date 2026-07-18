from django.contrib import admin

# Register your models here.
#from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
#from .models import 





'''
from django.contrib import admin
from .models import PaiementEmploye


@admin.register(PaiementEmploye)
class PaiementEmployeAdmin(admin.ModelAdmin):

    list_display = (
        'id',
        'employe_nom',
        'total_services',
        'date_paiement'
    )

    def employe_nom(self, obj):
        return obj.employe.nom

    employe_nom.short_description = "Employé"






@admin.register(RecuClient)
class RecuClientAdmin(admin.ModelAdmin):
    # Colonnes affichées dans la liste principale
    list_display = ('numero_recu', 'date', 'client_nom_display', 'total_global', 'mode_paiement', 'user')
    
    # Filtres sur le côté droit
    list_filter = ('mode_paiement', 'date', 'user')
    
    # Barre de recherche (très utile pour retrouver un reçu par son numéro ou nom client)
    search_fields = ('numero_recu', 'numero_groupe')
    
    # Organisation des champs dans le formulaire d'édition
    fieldsets = (
        ('Informations Générales', {
            'fields': ('numero_recu', 'numero_groupe', 'date')
        }),
        ('Détails Financiers', {
            'fields': ('total_global', 'mode_paiement', 'user')
        }),
    )
    
    # Champs en lecture seule (pour éviter de modifier le total ou la date manuellement)
    readonly_fields = ('date', 'numero_groupe')

    def client_nom_display(self, obj):
        """Récupère le nom du client depuis le premier paiement lié"""
        premier_paiement = PaiementEmploye.objects.filter(numero_groupe=obj.numero_groupe).first()
        return premier_paiement.client_nom if premier_paiement else "N/A"
    
    client_nom_display.short_description = "Nom du Client"
    '''





from django.contrib import admin
from .models import PaiementEmploye, RecuClient  # <-- Ajouté RecuClient ici
'''
@admin.register(PaiementEmploye)
class PaiementEmployeAdmin(admin.ModelAdmin):
    list_display = (
        'id', 
        'employe_nom', 
        'client_nom', 
        'display_services', # On ajoute la liste des services ici
        'total_services', 
        'date_paiement'
    )

    # Optimisation : charge les services et l'employé en une seule requête SQL
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('employe').prefetch_related('services')

    def employe_nom(self, obj):
        return obj.employe.nom if obj.employe else "---"
    employe_nom.short_description = "Employé"

    def display_services(self, obj):
        """Affiche les noms des services sous forme de texte séparé par des virgules"""
        return ", ".join([s.nom for s in obj.services.all()])
    display_services.short_description = "Services choisis"

@admin.register(RecuClient)
class RecuClientAdmin(admin.ModelAdmin):
    list_display = ('numero_recu', 'date', 'client_nom_display', 'total_global', 'mode_paiement', 'user')
    list_filter = ('mode_paiement', 'date', 'user')
    search_fields = ('numero_recu', 'numero_groupe')
    
    fieldsets = (
        ('Informations Générales', {
            'fields': ('numero_recu', 'numero_groupe', 'date')
        }),
        ('Détails Financiers', {
            'fields': ('total_global', 'mode_paiement', 'user')
        }),
    )
    
    readonly_fields = ('date', 'numero_groupe')

    def client_nom_display(self, obj):
        """Récupère le nom du client depuis le premier paiement lié"""
        # Utilisation de .only() pour être plus léger en mémoire
        premier_paiement = PaiementEmploye.objects.filter(
            numero_groupe=obj.numero_groupe
        ).only('client_nom').first()
        return premier_paiement.client_nom if premier_paiement else "N/A"
    
    client_nom_display.short_description = "Nom du Client"

    '''


@admin.register(PaiementEmploye)
class PaiementEmployeAdmin(admin.ModelAdmin):
    list_display = (
        'id', 
        'employe_nom', 
        'client_nom', 
        'display_services', 
        'total_services',
        'provenance_pack',
        'date_paiement'
    )

    # Optimisation : On ajoute 'employe__user' pour charger les noms d'un coup
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('employe__user').prefetch_related('services')

    # CORRECTION ICI
    def employe_nom(self, obj):
        if obj.employe and obj.employe.user:
            # On récupère le nom complet via l'objet User lié
            return f"{obj.employe.user.first_name} {obj.employe.user.last_name}"
        return "---"
    employe_nom.short_description = "Employé"
    # Permet de trier la colonne par le nom de famille de l'utilisateur
    employe_nom.admin_order_field = 'employe__user__last_name'

    def display_services(self, obj):
        return ", ".join([s.nom for s in obj.services.all()])
    display_services.short_description = "Services choisis"

@admin.register(RecuClient)
class RecuClientAdmin(admin.ModelAdmin):
    list_display = ('numero_recu', 'date', 'client_nom_display', 'total_global', 'mode_paiement', 'user')
    list_filter = ('mode_paiement', 'date', 'user')
    search_fields = ('numero_recu', 'numero_groupe')
    
    # ... le reste de ta configuration RecuClient est correcte ...
    
    def client_nom_display(self, obj):
        premier_paiement = PaiementEmploye.objects.filter(
            numero_groupe=obj.numero_groupe
        ).only('client_nom').first()
        return premier_paiement.client_nom if premier_paiement else "N/A"
    
    client_nom_display.short_description = "Nom du Client"