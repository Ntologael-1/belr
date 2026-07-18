import os
import django
import random
from decimal import Decimal
from datetime import datetime, timedelta, timezone as dt_timezone

# 1. INITIALISATION DE L'ENVIRONNEMENT DJANGO
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "my_shop.settings")
django.setup()

from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import transaction
from inventaire.models import (
    CategorieProduit, Produit, MouvementStock, 
    ChargeExploitation, PaiementCharge, StockMensuelSnapshot,
    DosageHistorique
)
from django.apps import apps
Service = apps.get_model('gestion', 'Service')

User = get_user_model()

def generer_donnees():
    print("🚀 Début de la génération complète des données BI (Inclus PAMP & Dosages)...")
    
    with transaction.atomic():
        # A. NETTOYAGE DES ANCIENNES TABLES
        DosageHistorique.objects.all().delete()
        StockMensuelSnapshot.objects.all().delete()
        MouvementStock.objects.all().delete()
        PaiementCharge.objects.all().delete()
        ChargeExploitation.objects.all().delete()
        Produit.objects.all().delete()
        CategorieProduit.objects.all().delete()
        
        # Optionnel : Si tu veux aussi réinitialiser les services pour éviter tout conflit de code unique :
        # Service.objects.all().delete()

        admin_user, _ = User.objects.get_or_create(
            username="manager_belr", 
            defaults={"is_staff": True, "is_superuser": True}
        )
        if _ : admin_user.set_password("password123"); admin_user.save()

        # B. CRÉATION DU CATALOGUE DE BASE
        cat_shampoing = CategorieProduit.objects.create(nom="Shampooings & Soins")
        cat_technique = CategorieProduit.objects.create(nom="Colorations & Oxydants")

        produits_data = [
            {"nom": "Shampooing Keratine Pro 1L", "categorie": cat_shampoing, "seuil": 4, "prix": 8500, "unite": "bouteille"},
            {"nom": "Soin Lissant Premium 500ml", "categorie": cat_shampoing, "seuil": 2, "prix": 12000, "unite": "pot"},
            {"nom": "Tube Coloration Majirel N°5", "categorie": cat_technique, "seuil": 10, "prix": 3500, "unite": "tube"},
        ]

        liste_produits = []
        for p in produits_data:
            prod = Produit.objects.create(
                nom=p["nom"],
                code=f"REF-{random.randint(1000, 9999)}",
                categorie=p["categorie"],
                seuil_alerte=Decimal(p["seuil"]),
                unite_mesure=p["unite"],
                quantite_stock=Decimal("0"),
                quantite_stock_theorique=Decimal("0")
            )
            liste_produits.append((prod, p["prix"]))

        # ✨ CORRECTION ICI : On utilise update_or_create avec un code explicite pour éviter les collisions de clés uniques
        service_soin, _ = Service.objects.update_or_create(
            nom="Soin Capillaire Premium",
            defaults={
                "prix": Decimal("15000.00"), 
                "duree": 45,
                "code": "SERV-SOIN-TEST"  # Forçage du code unique si ton modèle en dépend
            }
        )
        service_colo, _ = Service.objects.update_or_create(
            nom="Coloration Expert",
            defaults={
                "prix": Decimal("25000.00"), 
                "duree": 60,
                "code": "SERV-COLO-TEST"
            }
        )

        # C. GÉNÉRATION DES FLUX CHRONOLOGIQUES SUR 2 MOIS
        maintenant = timezone.now()
        mois_annees = [
            ((maintenant - timedelta(days=30)).month, (maintenant - timedelta(days=30)).year),
            (maintenant.month, maintenant.year)
        ]

        for mois, annee in mois_annees:
            print(f" 📅 Traitement des stocks et analyses pour la période : {mois}/{annee}")
            
            # 1. Remplissage des charges d'exploitation
            charge = ChargeExploitation.objects.create(
                type_charge="ENEO",
                libelle=f"Facture Électricité ENEO - {mois}/{annee}",
                montant_total=Decimal("45000"),
                date_echeance=datetime(annee, mois, 10).date()
            )
            PaiementCharge.objects.create(charge=charge, montant_verse=Decimal("45000"), mode_paiement="MOMO")

            # 2. Flux de mouvements de stock & Données financières
            for prod, prix_base in liste_produits:
                
                # Étape A: Entrée Achat (Initialise le PAMP)
                qte_entree = Decimal("20.00")
                mouv_entree = MouvementStock.objects.create(
                    produit=prod,
                    type_mouvement='ENTREE',
                    quantite=qte_entree,
                    prix_achat_unitaire=Decimal(prix_base),
                    created_by=admin_user,
                    notes=f"Achat stock début de mois {mois}/{annee}"
                )
                MouvementStock.objects.filter(pk=mouv_entree.pk).update(
                    date_mouvement=datetime(annee, mois, 2, 9, 0, tzinfo=dt_timezone.utc)
                )

                # Étape B: Sortie Consommation Prestation
                qte_sortie = Decimal("5.00")
                mouv_sortie = MouvementStock.objects.create(
                    produit=prod,
                    type_mouvement='SORTIE',
                    quantite=qte_sortie,
                    is_automatique=True,
                    created_by=admin_user,
                    notes=f"Sorties automatiques prestations {mois}/{annee}"
                )
                MouvementStock.objects.filter(pk=mouv_sortie.pk).update(
                    date_mouvement=datetime(annee, mois, 15, 14, 0, tzinfo=dt_timezone.utc)
                )

                # Étape C: Ajustement & fixation finale des stocks du produit
                prod.quantite_stock = Decimal("15.00")
                prod.quantite_stock_theorique = Decimal("15.00")
                prod.prix_achat_moyen = Decimal(prix_base)
                prod.dernier_prix_achat = Decimal(prix_base)
                prod.valeur_stock_totale = prod.quantite_stock * prod.prix_achat_moyen
                prod.save()

                # 3. FIXATION ET REMPLISSAGE FORCE DU SNAPSHOT MENSUEL BI
                StockMensuelSnapshot.objects.update_or_create(
                    produit=prod,
                    mois=mois,
                    annee=annee,
                    defaults={
                        'quantite_initiale_reelle': Decimal("0.00"),
                        'quantite_initiale_theorique': Decimal("0.00"),
                        'quantite_finale_reelle': prod.quantite_stock,
                        'quantite_finale_theorique': prod.quantite_stock_theorique,
                        'pamp_historique': prod.prix_achat_moyen  
                    }
                )

                # 4. REMPLISSAGE DE LA TABLE DOSAGE HISTORIQUE
                service_choisi = service_colo if prod.categorie == cat_technique else service_soin
                DosageHistorique.objects.update_or_create(
                    produit=prod,
                    service=service_choisi,
                    mois=mois,
                    annee=annee,
                    defaults={
                        'quantite_figee': Decimal("0.075") if prod.categorie == cat_technique else Decimal("0.050")
                    }
                )

    print("🎉 Base nettoyée et remplie avec succès ! Tout est prêt pour vos analyses.")

if __name__ == "__main__":
    generer_donnees()