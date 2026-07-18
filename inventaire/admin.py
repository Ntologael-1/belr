from django.contrib import admin
from .models import  PaiementCharge

# Register your models here.



from django.contrib import admin
from .models import CategorieProduit, Produit, MouvementStock, ConsommableService, ChargeExploitation

class ConsommableInline(admin.TabularInline):
    model = ConsommableService
    extra = 1

@admin.register(Produit)
class ProduitAdmin(admin.ModelAdmin):
    list_display = ('nom', 'quantite_stock_theorique', 'quantite_stock', 'prix_achat_moyen', 'valeur_stock_totale', 'est_en_alerte_badge')
    list_filter = ('categorie', 'actif', 'est_carburant')
    search_fields = ('nom', 'code')
    readonly_fields = ('quantite_stock', 'prix_achat_moyen', 'valeur_stock_totale')
    
    def est_en_alerte_badge(self, obj):
        from django.utils.html import format_html
        if obj.est_en_alerte:
            return format_html('<span style="color: red; font-weight: bold;">⚠️ Alerte</span>')
        return format_html('<span style="color: green;">Optimal</span>')
    est_en_alerte_badge.short_description = "Statut Stock"

@admin.register(MouvementStock)
class MouvementAdmin(admin.ModelAdmin):
    list_display = ('date_mouvement', 'produit', 'type_mouvement', 'quantite','pamp_historique' ,'quantite_apres', 'created_by')
    list_filter = ('type_mouvement', 'date_mouvement','is_automatique')
    readonly_fields = ('quantite_avant', 'quantite_apres', 'date_mouvement')

#@admin.register(ChargeExploitation)
# class ChargeAdmin(admin.ModelAdmin):
#     list_display = ('type_charge', 'montant', 'periode', 'date_facture', 'est_payee')
#     list_editable = ('est_payee',)
#     list_filter = ('type_charge', 'est_payee')







@admin.register(ChargeExploitation)
class ChargeExploitationAdmin(admin.ModelAdmin):
    # On utilise les nouveaux noms de champs :
    list_display = ('libelle', 'type_charge', 'montant_total', 'date_echeance', 'est_payee')
    list_filter = ('type_charge', 'est_payee', 'date_echeance')
    search_fields = ('libelle',)
    date_hierarchy = 'date_echeance'

@admin.register(PaiementCharge)
class PaiementChargeAdmin(admin.ModelAdmin):
    list_display = ('charge', 'montant_verse', 'date_paiement', 'mode_paiement')
    list_filter = ('mode_paiement', 'date_paiement')





from django.contrib import admin
from django.utils.html import format_html
from .models import  StockMensuelSnapshot

@admin.register( StockMensuelSnapshot)
class  StockMensuelSnapshot(admin.ModelAdmin):
    # 1. Colonnes affichées dans la liste globale
    list_display = (
        'get_periode', 
        'produit', 
        'pamp_historique',
        'quantite_initiale_reelle', 
        'quantite_initiale_theorique',
        'valeur_initiale_estimee'  # Calcul financier du stock de départ
    )
    
    # 2. Filtres latéraux pour naviguer dans l'historique des mois
    list_filter = ('annee', 'mois', 'produit__categorie')
    
    # 3. Barre de recherche (par nom ou code de produit)
    search_fields = ('produit__nom', 'produit__code')
    
    # 4. Tri par défaut (du mois le plus récent au plus ancien)
    ordering = ('-annee', '-mois', 'produit__nom')
    
    # 5. Optimisation SQL pour éviter les requêtes répétitives (problème N+1)
    list_select_related = ('produit',)
    
    # 6. Protection des données : Verrouillage en lecture seule pour protéger le BI
    # (Supprime ou commente cette ligne si tu veux pouvoir éditer les valeurs à la main)
    readonly_fields = ('quantite_initiale_reelle', 'quantite_initiale_theorique')

    # --- FONCTIONS D'AFFICHAGE PERSONNALISÉES ---

    def get_periode(self, obj):
        """Affiche la période sous un format lisible (ex: 05 / 2026)."""
        return format_html(f"📅 <b>{obj.mois:02d} / {obj.annee}</b>")
    get_periode.short_description = "Période"
    get_periode.admin_order_field = 'annee'

    def valeur_initiale_estimee(self, obj):
        """Estime la valeur financière du stock au premier jour du mois (Quantité * PAMP actuel)."""
        pamp = obj.produit.prix_achat_moyen or 0
        valeur = obj.quantite_initiale_reelle * pamp
        return format_html(f'<span style="color: #2c3e50; font-weight: 500;">{valeur:,.2f} FCFA</span>')
    valeur_initiale_estimee.short_description = "Valeur Initiale"