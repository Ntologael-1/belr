from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from .models import PaiementEmploye

from django.db.models.signals import m2m_changed, post_delete
from django.dispatch import receiver
from django.db.models import Sum
from decimal import Decimal, ROUND_HALF_UP
from .models import PaiementEmploye, RecuClient

from decimal import Decimal, ROUND_HALF_UP
from django.db.models import Sum
from django.db.models.signals import m2m_changed, post_delete
from django.dispatch import receiver
from django.core.cache import cache
from django.utils import timezone

# Importe tes modèles selon leur emplacement réel
from .models import PaiementEmploye, RecuClient 
from inventaire.models import MouvementStock

def invalider_cache_dashboard():
    """Supprime le cache du dashboard pour forcer le recalcul au prochain rechargement"""
    today = timezone.now().date()
    cache_key = f"dashboard_data_{today}"
    cache.delete(cache_key)

@receiver(m2m_changed, sender=PaiementEmploye.services.through)
def update_total_services(sender, instance, action, **kwargs):
    """
    Calcule le montant par employé et synchronise le total du reçu client.
    Gère la proratisation isolée par pack_instance_id.
    """
    if action in ["post_add", "post_remove", "post_clear"]:
        
        # --- A. LOGIQUE DE PRORATA (PACKS) ---
        if instance.provenance_pack and instance.pack_instance_id:
            prix_total_pack = Decimal(str(instance.provenance_pack.prix))
            
            intervenants_du_pack = PaiementEmploye.objects.filter(
                numero_groupe=instance.numero_groupe,
                pack_instance_id=instance.pack_instance_id
            ).prefetch_related('services')

            somme_theorique = Decimal('0')
            for p in intervenants_du_pack:
                somme_theorique += sum(Decimal(str(s.prix)) for s in p.services.all())

            if somme_theorique > 0:
                for p in intervenants_du_pack:
                    prix_catalogue_p = sum(Decimal(str(s.prix)) for s in p.services.all())
                    
                    quote_part = (prix_catalogue_p / somme_theorique) * prix_total_pack
                    quote_part = quote_part.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                    
                    PaiementEmploye.objects.filter(id=p.id).update(total_services=quote_part)

        # --- B. CAS SERVICE SIMPLE ---
        elif not instance.provenance_pack:
            total_service_simple = sum(Decimal(str(s.prix)) for s in instance.services.all())
            PaiementEmploye.objects.filter(id=instance.id).update(
                total_services=total_service_simple.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            )

        instance.refresh_from_db()

        # --- C. MISE À JOUR DU REÇU CLIENT ---
        update_recu_total(instance.numero_groupe)

@receiver(post_delete, sender=PaiementEmploye)
def update_recu_on_delete(sender, instance, **kwargs):
    """
    Recalcule la facture globale, supprime les mouvements de stock automatiques 
    liés et invalide le cache si un paiement d'employé est supprimé.
    """
    # 🌟 SÉCURITÉ BI : Nettoyage des mouvements automatiques liés à CE paiement
    # On cherche la chaîne exacte (Paiement #ID) que le système a écrit à l'ajout
    mouvements_fantomes = MouvementStock.objects.filter(
        type_mouvement='SORTIE',
        is_automatique=True,
        notes__icontains=f"(Paiement #{instance.id})"  # 🎯 Correspondance exacte avec ton auto_consommation_stock
    )
    
    if mouvements_fantomes.exists():
        mouvements_fantomes.delete()

    # Ton ancienne logique de mise à jour du reçu client
    if instance.numero_groupe:
        update_recu_total(instance.numero_groupe)
        
    # Invalidation du cache du dashboard
    invalider_cache_dashboard()

def update_recu_total(numero_groupe):
    """
    Calcule la somme de tous les paiements (total_services) du groupe 
    et met à jour le montant global dans RecuClient.
    Invalide également le cache du dashboard.
    """
    if not numero_groupe:
        return

    # Agrégation de tous les montants
    resultat = PaiementEmploye.objects.filter(
        numero_groupe=numero_groupe
    ).aggregate(total=Sum('total_services'))
    
    nouveau_total = resultat['total'] or Decimal('0.00')

    # Mise à jour finale du reçu pour BEL'R
    RecuClient.objects.filter(numero_groupe=numero_groupe).update(
        total_global=nouveau_total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    )

    # 🚨 CRITIQUE : Puisque .update() est utilisé, on force manuellement 
    # l'invalidation du cache pour que le dashboard prenne en compte cette vente
    invalider_cache_dashboard()