from decimal import Decimal
from django.db.models import Sum
from .models import StockMensuelSnapshot, Produit, MouvementStock

def executer_cloture_mensuelle(mois, annee):
    """
    Calcule et fige en base de données le snapshot d'un mois précis.
    Le stock final de ce mois deviendra le stock de départ du mois suivant.
    """
    produits = Produit.objects.all()
    
    # Trouver le mois précédent pour connaître le point de départ
    mois_prec = 12 if mois == 1 else mois - 1
    annee_prec = annee - 1 if mois == 1 else annee

    for produit in produits:
        # Récupération du point de départ historique fige
        snapshot_prec = StockMensuelSnapshot.objects.filter(
            produit=produit, mois=mois_prec, annee=annee_prec
        ).first()
        
        stock_initial_r = snapshot_prec.stock_final_reel if snapshot_prec else Decimal('0')
        stock_initial_t = snapshot_prec.stock_final_theorique if snapshot_prec else Decimal('0')
        
        # Mouvements du mois à clôturer
        mouvements = MouvementStock.objects.filter(
            produit=produit, date_mouvement__month=mois, date_mouvement__year=annee
        )
        
        entrees = mouvements.filter(type_mouvement='ENTREE').aggregate(s=Sum('quantite'))['s'] or Decimal('0')
        conso_theo = mouvements.filter(type_mouvement='SORTIE', is_automatique=True).aggregate(s=Sum('quantite'))['s'] or Decimal('0')
        conso_manuelle = mouvements.filter(type_mouvement='SORTIE', is_automatique=False).aggregate(s=Sum('quantite'))['s'] or Decimal('0')
        
        # Calcul des stocks finaux (Règles métier BEL'R)
        stock_final_r = stock_initial_r + entrees - conso_manuelle
        stock_final_t = stock_initial_t + entrees - conso_theo
        
        # Sauvegarde ou mise à jour
        StockMensuelSnapshot.objects.update_or_create(
            produit=produit, mois=mois, annee=annee,
            defaults={
                'stock_final_reel': stock_final_r,
                'stock_final_theorique': stock_final_t
            }
        )