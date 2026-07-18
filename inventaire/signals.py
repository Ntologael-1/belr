from django.db.models.signals import m2m_changed
from django.dispatch import receiver
# Remplace 'gestion' et 'inventaire' par les noms réels de tes apps
from rendezvous.models import PaiementEmploye 
from inventaire.models import MouvementStock, ConsommableService
from django.db.models.signals import pre_save, post_delete
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from django.utils import timezone

from datetime import timedelta
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models.signals import post_delete, pre_save
from django.dispatch import receiver
from django.utils import timezone
from decimal import Decimal

# 🌟 IMPORTS DES MODÈLES DE L'APPLICATION INVENTAIRE
from inventaire.models import (
    ConsommableService,
    DosageHistorique,
    MouvementStock,
    Produit,
    StockMensuelSnapshot,
)

# 🌟 IMPORTS DES MODÈLES DE L'APPLICATION RENDEZVOUS
from rendezvous.models import PaiementEmploye

# 🌟 IMPORTS INTER-APPS STRICTS POUR BEL'R DosageHistorique
from inventaire.models import ConsommableService, DosageHistorique,MouvementStock
from rendezvous.models import PaiementEmploye

@receiver(m2m_changed, sender=PaiementEmploye.services.through)
def auto_consommation_stock(sender, instance, action, **kwargs):
    """
    Dès qu'un service est ajouté à un paiement, on crée un mouvement théorique.
    """
    if action == "post_add":
        for service in instance.services.all():
            # On récupère la recette liée au service
            recettes = ConsommableService.objects.filter(service=service)
            
            for item in recettes:
                MouvementStock.objects.create(
                    produit=item.produit,
                    type_mouvement='SORTIE',
                    quantite=item.quantite_prevue,
                    is_automatique=True, # <--- Marqué comme théorique
                    notes=f"Auto-conso: {service.nom} (Paiement #{instance.id})",
                    created_by=None # Système
                )






@receiver(pre_save, sender=ConsommableService)
def verrouiller_dosage_mensuel(sender, instance, **kwargs):
    if instance.id:
        ancien_objet = ConsommableService.objects.get(id=instance.id)
        
        if ancien_objet.quantite_prevue != instance.quantite_prevue:
            maintenant = timezone.now()
            
            # 🛑 RÈGLE 1 : Bloqué après le 10 du mois
            if maintenant.day > 10:
                raise ValidationError(
                    f"Action refusée : Nous sommes le {maintenant.day}. "
                    "Les modifications de dosages sont bloquées après le 10 du mois."
                )
            
            # 🛑 RÈGLE 2 : Une seule modification par mois
            deja_modifie = DosageHistorique.objects.filter(
                produit=instance.produit, service=instance.service,
                mois=maintenant.month, annee=maintenant.year
            ).exists()
            
            if deja_modifie:
                raise ValidationError(
                    "Action refusée : Vous avez déjà modifié ce dosage une fois ce mois-ci."
                )
            
            # On crée une trace pour verrouiller le mois
            DosageHistorique.objects.create(
                produit=ancien_objet.produit, service=ancien_objet.service,
                quantite_figee=instance.quantite_prevue, # Sera écrasé par la fin de mois si nécessaire
                mois=maintenant.month, annee=maintenant.year
            )




from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from .models import MouvementStock, StockMensuelSnapshot



@receiver(pre_save, sender=MouvementStock)
def detecter_et_creer_debut_de_mois(sender, instance, **kwargs):
    date_mv = instance.date_mouvement or timezone.now()
    mois_actuel = date_mv.month
    annee_actuelle = date_mv.year

    # 1. Vérification ultra-rapide via un index BDD
    deja_initialise = StockMensuelSnapshot.objects.filter(
        produit=instance.produit,
        mois=mois_actuel,
        annee=annee_actuelle
    ).exists()

    if not deja_initialise:
        with transaction.atomic():
            # --- A. PRÉPARATION DES SNAPSHOTS EN BULK (1 SEULE REQUÊTE) ---
            produits = Produit.objects.all()
            
            date_prec = date_mv.replace(day=1) - timedelta(days=1)
            
            # On récupère TOUS les snapshots du mois dernier d'un coup pour éviter les requêtes dans la boucle
            snaps_prec_dict = {
                s.produit_id: s 
                for s in StockMensuelSnapshot.objects.filter(mois=date_prec.month, annee=date_prec.year)
            }

            snapshots_a_creer = []
            for p in produits:
                snap_prec = snaps_prec_dict.get(p.id)
                qte_init_reelle = snap_prec.quantite_finale_reelle if snap_prec else p.quantite_stock
                qte_init_theorique = snap_prec.quantite_finale_theorique if snap_prec else p.quantite_stock

                snapshots_a_creer.append(
                    StockMensuelSnapshot(
                        produit=p,
                        mois=mois_actuel,
                        annee=annee_actuelle,
                        quantite_initiale_reelle=qte_init_reelle,
                        quantite_initiale_theorique=qte_init_theorique,
                        quantite_finale_reelle=qte_init_reelle,
                        quantite_finale_theorique=qte_init_theorique,
                        pamp_historique=p.prix_achat_moyen or Decimal('0')
                    )
                )
            
            # 🔥 Insertion de masse en BDD (Évite les doublons avec ignore_conflicts)
            StockMensuelSnapshot.objects.bulk_create(snapshots_a_creer, ignore_conflicts=True)


            # --- B. PRÉPARATION DES DOSAGES EN BULK (1 SEULE REQUÊTE) ---
            # select_related évite que Django ne retourne chercher le produit/service en BDD pour chaque ligne
            recettes_actuelles = ConsommableService.objects.all().select_related('produit', 'service')
            
            dosages_a_creer = []
            for r in recettes_actuelles:
                dosages_a_creer.append(
                    DosageHistorique(
                        produit=r.produit,
                        service=r.service,
                        mois=mois_actuel,
                        annee=annee_actuelle,
                        quantite_figee=r.quantite_prevue
                    )
                )
            
            # 🔥 Insertion de masse en BDD
            DosageHistorique.objects.bulk_create(dosages_a_creer, ignore_conflicts=True)