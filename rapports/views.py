
# ==========================================
# 1. Standard Library Imports
# ==========================================
import calendar
from calendar import monthrange
from collections import defaultdict
import datetime
from datetime import date, timedelta
from decimal import Decimal
import json
import random
import uuid

# ==========================================
# 2. Third-Party Imports (dateutil)
# ==========================================
from dateutil.relativedelta import relativedelta

# ==========================================
# 3. Django Core Imports
# ==========================================
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import models
from django.db.models import (
    Avg, Count, DecimalField, ExpressionWrapper, F, Prefetch, Q, Sum
)
from django.db.models.functions import ExtractHour, TruncDay, TruncMonth
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.timezone import now

# ==========================================
# 4. Local Apps Imports (🚨 Alerte Imports Circulaires)
# ==========================================
from authentification.decorator import employe_required, gerant_only, manager_required
from clients.models import Client
from employes.models import Employe
from gestion.models import Service

# Si ce fichier de vues appartient à l'application 'inventaire' ou 'rendezvous',
# importer leurs modèles ici peut créer un import circulaire.
# S'il y a un plantage au démarrage, déplace ces imports directement à l'intérieur
# des fonctions/views spécifiques qui les utilisent.
from inventaire.models import (
    ChargeExploitation, ConsommableService, MouvementStock, 
    PaiementCharge, Produit, StockMensuelSnapshot
)
from rendezvous.models import PaiementEmploye, RecuClient

# Importations relatives (Modèles locaux à cette application)
from .models import DosageMensuelSnapshot, PerformanceMensuelleSnapshot,RapportMensuelConsolide





import datetime
import json
from decimal import Decimal
from calendar import monthrange
from dateutil.relativedelta import relativedelta

from django.db.models import Sum, Count, F, ExpressionWrapper, DecimalField
from django.utils import timezone
from django.shortcuts import render

# Importe tes décorateurs et modèles selon la structure de ton projet
# from .decorators import gerant_only
# from .models import RecuClient, PaiementCharge, Employe, PaiementEmploye, MouvementStock, Produit, StockMensuelSnapshot, ConsommableService, PerformanceMensuelleSnapshot






@gerant_only
def dashboard_bi_couts(request):
    # ====================================================================
    # 1. ANCRAGE TEMPOREL (12 DERNIERS MOIS)
    # ====================================================================
    today = datetime.date.today()
    date_ref = datetime.date(today.year, today.month, 1)
    date_debut_12_mois = date_ref - relativedelta(months=11)

    periodes = []
    chart_labels = []
    mois_noms = ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin", "Juil", "Août", "Sept", "Oct", "Nov", "Déc"]
    
    for i in reversed(range(12)):
        d = date_ref - relativedelta(months=i)
        periodes.append((d.year, d.month))
        chart_labels.append(f"{mois_noms[d.month-1]} {str(d.year)[2:]}")

    # ====================================================================
    # 2. PRÉ-AGRÉGATION EN MÉMOIRE (CORRIGÉE TEMPS RÉEL)
    # ====================================================================
    maintenant = timezone.now()

    ca_par_mois = RecuClient.objects.filter(
        date__gte=date_debut_12_mois, date__lte=maintenant, demande_suppression=False
    ).annotate(month_group=TruncMonth('date')).values('month_group').annotate(total=Sum('total_global'))
    dict_ca = {f"{r['month_group'].year}-{r['month_group'].month}": r['total'] for r in ca_par_mois}

    charges_par_mois = PaiementCharge.objects.filter(
        date_paiement__gte=date_debut_12_mois, date_paiement__lte=maintenant.date()
    ).exclude(charge__type_charge='SALAIRE_FIXE').annotate(month_group=TruncMonth('date_paiement')).values('month_group').annotate(total=Sum('montant_verse'))
    dict_charges = {f"{r['month_group'].year}-{r['month_group'].month}": r['total'] for r in charges_par_mois}
    
    employes_actifs = Employe.objects.filter(actif=True).select_related('user')
    salaires_base_actuels = sum(emp.salaire_base or Decimal('0') for emp in employes_actifs)
    
    fixes_par_mois = PaiementCharge.objects.filter(
        date_paiement__gte=date_debut_12_mois, date_paiement__lte=maintenant.date(), charge__type_charge='SALAIRE_FIXE'
    ).annotate(month_group=TruncMonth('date_paiement')).values('month_group').annotate(total=Sum('montant_verse'))
    dict_fixes = {f"{r['month_group'].year}-{r['month_group'].month}": r['total'] for r in fixes_par_mois}

    prestations_hist = PaiementEmploye.objects.filter(
        date_paiement__gte=date_debut_12_mois, date_paiement__lte=maintenant.date()
    ).annotate(month_group=TruncMonth('date_paiement')).values('month_group', 'employe_id').annotate(
        total_ca_calc=Sum(F('total_services') * F('quantite'))
    )
    
    dict_com_mensuelle = {}
    for p in prestations_hist:
        key = f"{p['month_group'].year}-{p['month_group'].month}"
        if key not in dict_com_mensuelle:
            dict_com_mensuelle[key] = {}
        dict_com_mensuelle[key][p['employe_id']] = p['total_ca_calc']

    tous_les_produits = list(Produit.objects.filter(actif=True))

    # 🔥 OPTIMISATION VITESSE GÉNIALE : On extrait TOUTES les fiches techniques en 1 seule requête SQL
    fiches_techniques = ConsommableService.objects.all()
    dict_fiches_techniques = {}
    for f in fiches_techniques:
        if f.produit_id not in dict_fiches_techniques:
            dict_fiches_techniques[f.produit_id] = []
        dict_fiches_techniques[f.produit_id].append(f)

    # ====================================================================
    # 3. STRUCTURES CHRONOLOGIQUES ET LOGISTIQUES
    # ====================================================================
    chart_benefices, chart_couts_reels, chart_couts_theoriques, chart_volume_global = [], [], [], []
    historique_ca_brut, historique_couts_bruts = [], []

    masse_salariale_actuelle = Decimal('0')
    charges_actuelles = Decimal('0')
    cout_stock_actuel = Decimal('0')
    cout_stock_theo_actuel = Decimal('0')

    dict_cumul_couts_produits = {p.id: Decimal('0.00') for p in tous_les_produits}
    dict_historique_produits_brut = {p.id: [0.0] * 12 for p in tous_les_produits}

    # ====================================================================
    # 4. SÉRIE CHRONOLOGIQUE FLUIDIFIÉE (ZÉRO REQUÊTE INTERNE)
    # ====================================================================
    for idx, (year, month) in enumerate(periodes):
        key = f"{year}-{month}"
        
        if month == 12:
            month_suiv, year_suiv = 1, year + 1
        else:
            month_suiv, year_suiv = month + 1, year

        _, last_day = monthrange(year, month)
        datetime_start = timezone.make_aware(timezone.datetime(year, month, 1, 0, 0, 0))
        datetime_end = timezone.make_aware(timezone.datetime(year, month, last_day, 23, 59, 59))

        h_ca = dict_ca.get(key, Decimal('0'))
        h_charges = dict_charges.get(key, Decimal('0'))
        h_fixes = dict_fixes.get(key, salaires_base_actuels if h_ca > 0 else Decimal('0'))
        
        h_commissions = Decimal('0')
        com_sub_dict = dict_com_mensuelle.get(key, {})
        for emp in employes_actifs:
            h_commissions += Decimal(str(emp.calculer_bonus(com_sub_dict.get(emp.id, Decimal('0')))))
            
        h_masse = h_fixes + h_commissions

        h_cout_reel_stock = Decimal('0')
        h_cout_theo_stock = Decimal('0')
        h_vol_global = Decimal('0')

        snapshots_mois = {s.produit_id: s for s in StockMensuelSnapshot.objects.filter(mois=month, annee=year)}
        snapshots_mois_suiv = {s.produit_id: s for s in StockMensuelSnapshot.objects.filter(mois=month_suiv, annee=year_suiv)}
        
        entrees_mois = {
            item['produit_id']: item['total'] for item in MouvementStock.objects.filter(
                type_mouvement='ENTREE', date_mouvement__range=[datetime_start, datetime_end]
            ).values('produit_id').annotate(total=Sum('quantite'))
        }
        
        sorties_inventaires_mois = {
            item['produit_id']: item['total'] for item in MouvementStock.objects.filter(
                type_mouvement='SORTIE', is_automatique=False, date_mouvement__range=[datetime_start, datetime_end]
            ).values('produit_id').annotate(total=Sum('quantite'))
        }

        ventes_services_mois = {
            item['services__id']: item['nb_ventes'] for item in PaiementEmploye.objects.filter(
                date_paiement__range=[datetime_start.date(), datetime_end.date()]
            ).values('services__id').annotate(nb_ventes=Count('id'))
        }

        # Calcul analytique ultra-rapide en RAM pure
        for p in tous_les_produits:
            pamp = p.prix_achat_moyen or Decimal('0.00')
            snap = snapshots_mois.get(p.id)
            entrees = entrees_mois.get(p.id, Decimal('0.00'))
            sorties_manuelles = sorties_inventaires_mois.get(p.id, Decimal('0.00'))
            
            if snap:
                stock_initial = snap.quantite_initiale_reelle
            else:
                stock_initial = p.quantite_stock if (month == today.month and year == today.year) else Decimal('0.00')

            if month == today.month and year == today.year:
                stock_final_reel = p.quantite_stock
            else:
                snap_suiv = snapshots_mois_suiv.get(p.id)
                stock_final_reel = snap_suiv.quantite_initiale_reelle if snap_suiv else ((stock_initial + entrees) - sorties_manuelles)

            quantite_consommee_reelle = max((stock_initial + entrees) - stock_final_reel, Decimal('0.00'))

            # Remplacement de la requête par une lecture du dictionnaire local en RAM
            if getattr(p, 'est_carburant', False):
                quantite_consommee_theorique = quantite_consommee_reelle
            else:
                conso_theo_dynamique = Decimal('0.00')
                # Lecture ultra-rapide du cache local
                for r in dict_fiches_techniques.get(p.id, []):
                    conso_theo_dynamique += r.quantite_prevue * ventes_services_mois.get(r.service_id, 0)
                quantite_consommee_theorique = conso_theo_dynamique

            cout_reel_produit = quantite_consommee_reelle * pamp
            cout_theo_produit = quantite_consommee_theorique * pamp

            h_cout_reel_stock += cout_reel_produit
            h_cout_theo_stock += cout_theo_produit
            h_vol_global += quantite_consommee_reelle

            dict_cumul_couts_produits[p.id] += cout_reel_produit
            dict_historique_produits_brut[p.id][idx] = float(quantite_consommee_reelle)

        h_depenses_reelles = h_masse + h_charges + h_cout_reel_stock
        h_depenses_theoriques = h_masse + h_charges + h_cout_theo_stock
        
        chart_benefices.append(float(h_ca - h_depenses_reelles))
        chart_couts_reels.append(float(h_depenses_reelles))
        chart_couts_theoriques.append(float(h_depenses_theoriques))
        chart_volume_global.append(float(h_vol_global))
        
        historique_ca_brut.append(h_ca)
        historique_couts_bruts.append(h_depenses_reelles)

        if idx == 11:
            masse_salariale_actuelle = h_masse
            charges_actuelles = h_charges
            cout_stock_actuel = h_cout_reel_stock
            cout_stock_theo_actuel = h_cout_theo_stock

    # ====================================================================
    # 5. TRI ET RÉSULTATS (RAM SEULEMENT)
    # ====================================================================
    produits_tries = sorted(tous_les_produits, key=lambda x: dict_cumul_couts_produits[x.id], reverse=True)[:5]
    top_produits_consommes = [{'id': p.id, 'nom_produit': p.nom, 'cout_total': float(dict_cumul_couts_produits[p.id])} for p in produits_tries]
    dict_historique_produits = {p.id: dict_historique_produits_brut[p.id] for p in produits_tries}

    # ====================================================================
    # 6. GRAPH DE CROISSANCE (REPRISE STRICTE DE TON ANCIEN CODE)
    # ====================================================================
    chart_croissance_benefices = [0.0]  # Ton point de départ initial
    chart_croissance_couts = [0.0]
    
    # Ton ancienne boucle qui parcourt à partir du deuxième mois (index 1)
    for idx in range(1, len(chart_benefices)):
        b_prec = chart_benefices[idx - 1]
        b_actuel = chart_benefices[idx]
        c_prec = chart_couts_reels[idx - 1]
        c_actuel = chart_couts_reels[idx]
        
        # Ta logique de calcul exacte pour le bénéfice
        if b_prec > 0:
            crois_b = ((b_actuel - b_prec) / b_prec) * 100
        else:
            crois_b = 0.0 if b_actuel == b_prec else (100.0 if b_actuel > b_prec else -100.0)
            
        # Ta logique de calcul exacte pour les coûts
        if c_prec > 0:
            crois_c = ((c_actuel - c_prec) / c_prec) * 100
        else:
            crois_c = 0.0 if c_actuel == c_prec else 100.0

        chart_croissance_benefices.append(round(crois_b, 2))
        chart_croissance_couts.append(round(crois_c, 2))

    # L'effet ciseaux et le diagnostic basés sur tes formules d'origine
    indice_ciseaux = round(chart_croissance_benefices[-1] - chart_croissance_couts[-1], 2)
    tendance_benefice = "En hausse" if indice_ciseaux >= 0 else "En baisse"
    statut_soutenabilite = "SAINE : Les bénéfices distancient les coûts" if indice_ciseaux >= 0 else "CRITIQUE : Les coûts augmentent plus vite que les bénéfices"
    ca_net_salon, ca_global = chart_benefices[-1], historique_ca_brut[-1]

    ecart_inventaire_mois = float(cout_stock_actuel - cout_stock_theo_actuel)
    taux_coulage = (ecart_inventaire_mois / float(cout_stock_actuel) * 100) if cout_stock_actuel > 0 else 0.0
    taux_effort = float((historique_couts_bruts[-1] / ca_global * 100) if ca_global > 0 else 0)

    mois_noms_complets = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]
    nom_du_mois_actuel = f"{mois_noms_complets[today.month - 1]} {today.year}"

    context = {
        'nom_du_mois_actuel': nom_du_mois_actuel, 'statut_soutenabilite': statut_soutenabilite, 'indice_ciseaux': indice_ciseaux, 'tendance_benefice': tendance_benefice,
        'ca_net_salon': float(ca_net_salon), 'ca_global': float(ca_global), 'taux_effort': taux_effort, 'top_produits_consommes': top_produits_consommes,
        'masse_salariale': float(masse_salariale_actuelle), 'total_charges': float(charges_actuelles),
        'cout_stock_reel': float(cout_stock_actuel), 'cout_stock_theorique': float(cout_stock_theo_actuel), 'ecart_inventaire_mois': ecart_inventaire_mois, 'taux_coulage': taux_coulage,
        'chart_labels_json': json.dumps(chart_labels), 'chart_benefices_json': json.dumps(chart_benefices), 'chart_couts_reels_json': json.dumps(chart_couts_reels),
        'chart_couts_theoriques_json': json.dumps(chart_couts_theoriques), 'chart_volume_global_json': json.dumps(chart_volume_global), 'dict_historique_produits_json': json.dumps(dict_historique_produits),
        'chart_croissance_benefices_json': json.dumps(chart_croissance_benefices), 'chart_croissance_couts_json': json.dumps(chart_croissance_couts),
    }
   
    return render(request, 'rapports/dashboard_bi.html', context)





@gerant_only
def rapport_global(request):
    today = timezone.now().date()

    # ====================================================================
    # 1. GESTION DE LA PÉRIODE & ANCRAGE TEMPOREL
    # ====================================================================
    try:
        selected_month = int(request.GET.get("month", today.month))
        selected_year = int(request.GET.get("year", today.year))
    except ValueError:
        selected_month, selected_year = today.month, today.year

    month_start = datetime.date(selected_year, selected_month, 1)
    _, last_day = monthrange(selected_year, selected_month)
    month_end = datetime.date(selected_year, selected_month, last_day)

    # Détermination des bornes pour les snapshots de clôture
    if selected_month == 12:
        month_suiv, year_suiv = 1, selected_year + 1
    else:
        month_suiv, year_suiv = selected_month + 1, selected_year

    # Bornes DateTime précises pour les mouvements de stocks
    datetime_start = timezone.make_aware(timezone.datetime(selected_year, selected_month, 1, 0, 0, 0))
    datetime_end = timezone.make_aware(timezone.datetime(selected_year, selected_month, last_day, 23, 59, 59))

    # ====================================================================
    # 2. BASES DE FILTRAGE OPTIMISÉES
    # ====================================================================
    recus_base = RecuClient.objects.filter(
        date__date__range=[month_start, month_end],
        demande_suppression=False
    )
    
    paiements_base = PaiementEmploye.objects.filter(
        date_paiement__date__range=[month_start, month_end]
    )

    # ====================================================================
    # 3. KPI GLOBAUX & COMPARAISON RÉTROACTIVE
    # ====================================================================
    ca_global = recus_base.aggregate(total=Sum("total_global"))["total"] or Decimal('0')
    total_tickets = recus_base.count()
    panier_moyen = ca_global / total_tickets if total_tickets > 0 else Decimal('0')

    # ---- CORRECTION DU MOIS PRÉCÉDENT ----
    last_month_end_date = month_start - datetime.timedelta(days=1)
    
    # 1. On crée des objets datetime complets (Heures, Minutes, Secondes)
    dt_prev_start = datetime.datetime(last_month_end_date.year, last_month_end_date.month, 1, 0, 0, 0)
    dt_prev_end = datetime.datetime(last_month_end_date.year, last_month_end_date.month, last_month_end_date.day, 23, 59, 59)
    
    # 2. On les rend "Timezone Aware" pour que Django lise parfaitement la base de données
    datetime_prev_start = timezone.make_aware(dt_prev_start)
    datetime_prev_end = timezone.make_aware(dt_prev_end)
    
    # 3. Filtrage direct et ultra-rapide sur le champ 'date' sans passer par '__date'
    ca_prev = RecuClient.objects.filter(
        date__range=[datetime_prev_start, datetime_prev_end],
        demande_suppression=False
    ).aggregate(total=Sum("total_global"))["total"] or Decimal('0')
    
    # Calcul de l'évolution (Inchangé mais maintenant basé sur un ca_prev réel)
    evolution_ca = ((ca_global - ca_prev) / ca_prev * 100) if ca_prev > 0 else Decimal('100')

    # Pénétration des Packs
    ca_packs = paiements_base.filter(provenance_pack__isnull=False).aggregate(
        total=Sum("total_services")
    )["total"] or Decimal('0')
    part_ca_packs = (ca_packs / ca_global * 100) if ca_global > 0 else Decimal('0')


    # ====================================================================
    # 4. PERFORMANCE EMPLOYÉS & MASSE SALARIALE SÉCURISÉE (Optimisé RAM)
    # ====================================================================
    stats_query = paiements_base.values('employe').annotate(
        ca_genere=Sum('total_services'),
        nb_actes=Count('id')
    )
    stats_map = {item['employe']: item for item in stats_query}
    
    employes_du_mois = Employe.objects.filter(
        Q(id__in=stats_map.keys()) | Q(actif=True)
    ).distinct().select_related('user')
    
    stats_employes = []
    total_masse_salariale = Decimal('0')

    # Vérification de la période (Présent/Futur vs Passé)
    est_mois_actuel_ou_futur = (selected_year > today.year) or (selected_year == today.year and selected_month >= today.month)

    for emp in employes_du_mois:
        data = stats_map.get(emp.id, {'ca_genere': 0, 'nb_actes': 0})
        ca_emp = Decimal(str(data['ca_genere'] or 0))
        
        if est_mois_actuel_ou_futur:
            # --- LE PRÉSENT : Mise à jour en continu ---
            snapshot_salaire, _ = PerformanceMensuelleSnapshot.objects.update_or_create(
                employe=emp,
                mois=selected_month,
                annee=selected_year,
                defaults={
                    'salaire_base_historique': emp.salaire_base or Decimal('0'),
                    'palier_1_ca_historique': emp.palier_1_ca or Decimal('0'),
                    'palier_1_percent_historique': emp.palier_1_percent or Decimal('0'),
                    'palier_2_ca_historique': emp.palier_2_ca or Decimal('0'),
                    'palier_2_percent_historique': emp.palier_2_percent or Decimal('0'),
                }
            )
        else:
            # --- LE PASSÉ : Lecture de l'historique figé ---
            snapshot_salaire = PerformanceMensuelleSnapshot.objects.filter(
                employe=emp, mois=selected_month, annee=selected_year
            ).first()
            
            # Si aucun snapshot n'existait pour ce mois passé, on fige une valeur de secours
            if not snapshot_salaire:
                vieux_paiement = paiements_base.filter(employe=emp).first()
                if vieux_paiement:
                    salaire_recupere = vieux_paiement.salaire_base_historique if hasattr(vieux_paiement, 'salaire_base_historique') else emp.salaire_base
                else:
                    salaire_recupere = emp.salaire_base

                snapshot_salaire = PerformanceMensuelleSnapshot.objects.create(
                    employe=emp,
                    mois=selected_month,
                    annee=selected_year,
                    salaire_base_historique=salaire_recupere,
                    palier_1_ca_historique=emp.palier_1_ca,
                    palier_1_percent_historique=emp.palier_1_percent,
                    palier_2_ca_historique=emp.palier_2_ca,
                    palier_2_percent_historique=emp.palier_2_percent
                )
        
        # Calcul du bonus
        bonus = Decimal(str(emp.calculer_bonus(
            ca_mensuel=ca_emp,
            p1_ca=snapshot_salaire.palier_1_ca_historique,
            p1_pct=snapshot_salaire.palier_1_percent_historique,
            p2_ca=snapshot_salaire.palier_2_ca_historique,
            p2_pct=snapshot_salaire.palier_2_percent_historique
        )))
        
        # Détermination du salaire fixe à appliquer (0 si aucun CA et aucun acte pour ce mois, sinon le salaire historique)
        salaire_base_historique = snapshot_salaire.salaire_base_historique if (ca_global > 0 or ca_emp > 0) else Decimal('0')
        salaire_total = salaire_base_historique + bonus
        total_masse_salariale += salaire_total

        stats_employes.append({
            "employe": emp,
            "salaire_fixe_historique": salaire_base_historique, # <--- AJOUT CRUCIAL ICI
            "ca_genere": ca_emp,
            "bonus": bonus,
            "salaire_total": salaire_total,
            "nb_actes": data['nb_actes'],
            "rentabilite": (ca_emp - salaire_total)
        })



    # ====================================================================
    # 5. COÛT LOGISTIQUE DES STOCKS (Équation Comptable Réelle)
    # ====================================================================
    recettes_actuelles = ConsommableService.objects.select_related('produit', 'service').all()
    for recette in recettes_actuelles:
        DosageMensuelSnapshot.objects.get_or_create(
            produit=recette.produit,
            service=recette.service,
            mois=selected_month,
            annee=selected_year,
            defaults={
                'quantite_prevue_historique': recette.quantite_prevue,
                'rendement_par_unite_historique': recette.rendement_par_unite,
            }
        )

    snapshots_mois = {s.produit_id: s for s in StockMensuelSnapshot.objects.filter(mois=selected_month, annee=selected_year)}
    snapshots_mois_suiv = {s.produit_id: s for s in StockMensuelSnapshot.objects.filter(mois=month_suiv, annee=year_suiv)}
    
    entrees_mois = {
        item['produit_id']: item['total'] for item in MouvementStock.objects.filter(
            type_mouvement='ENTREE', date_mouvement__range=[datetime_start, datetime_end]
        ).values('produit_id').annotate(total=Sum('quantite'))
    }

    total_cout_produits = Decimal('0')
    tous_les_produits = Produit.objects.filter(actif=True)

    for p in tous_les_produits:
        pamp = p.prix_achat_moyen or Decimal('0')
        snap = snapshots_mois.get(p.id)
        entrees = entrees_mois.get(p.id, Decimal('0'))
        
        stock_initial = snap.quantite_initiale_reelle if snap else (p.quantite_stock if (selected_month == today.month and selected_year == today.year) else Decimal('0'))
        
        if selected_month == today.month and selected_year == today.year:
            stock_final_reel = p.quantite_stock
        else:
            snap_suiv = snapshots_mois_suiv.get(p.id)
            stock_final_reel = snap_suiv.quantite_initiale_reelle if snap_suiv else (stock_initial + entrees)

        quantite_consommee_reelle = (stock_initial + entrees) - stock_final_reel
        if quantite_consommee_reelle < 0: 
            quantite_consommee_reelle = Decimal('0')
            
        total_cout_produits += (quantite_consommee_reelle * pamp)

    # ====================================================================
    # 6. CHARGES D'EXPLOITATION NETTES
    # ====================================================================
    total_charges_exploitation = PaiementCharge.objects.filter(
        date_paiement__range=[month_start, month_end]
    ).exclude(charge__type_charge='SALAIRE_FIXE').aggregate(total=Sum('montant_verse'))['total'] or Decimal('0')

    # ====================================================================
    # 7. CONSOLIDATION FINANCIÈRE DE LA RENTABILITÉ NETTE
    # ====================================================================
    total_depenses_globales = total_masse_salariale + total_cout_produits + total_charges_exploitation
    ca_net_salon = ca_global - total_depenses_globales
    taux_effort = (total_depenses_globales / ca_global * 100) if ca_global > 0 else Decimal('0')

    # ====================================================================
    # 8. TOP SERVICES VENDUS
    # ====================================================================
    top_services = paiements_base.values("services__nom", "services__code").annotate(
        total_ca=Sum("total_services"),
        volume=Count("id")
    ).order_by("-total_ca")[:8]

    # ====================================================================
    # 9. DONNÉES GRAPHIQUES NETTOYÉES POUR CHART.JS (Avec jours à 0)
    # ====================================================================
    daily_query = recus_base.annotate(day=TruncDay('date')) \
        .values('day').annotate(total=Sum('total_global')).order_by('day')
    
    dict_activite = {item['day'].strftime('%Y-%m-%d'): item['total'] for item in daily_query if item['day']}

    labels_jours = []
    donnees_ca = []
    
    for jour in range(1, last_day + 1):
        date_boucle = datetime.date(selected_year, selected_month, jour)
        date_key = date_boucle.strftime('%Y-%m-%d')
        
        labels_jours.append(date_boucle.strftime('%d')) # Conserve le format '%d' d'origine pour les jours (01, 02...)
        total_du_jour = dict_activite.get(date_key, Decimal('0'))
        donnees_ca.append(float(total_du_jour))

    # Répartition des modes de paiement
    paiement_modes = recus_base.values('mode_paiement').annotate(total=Count('id'))

    # ====================================================================
    # 10. CONTEXTE STRUCTURE INITIALE RECONSTITUÉ
    # ====================================================================
    context = {
        "period": {
            "month": selected_month,
            "year": selected_year,
            "month_name": month_start.strftime("%B"),
        },
        "kpi": {
            "ca_brut": ca_global,
            "ca_prev": ca_prev,
            "evolution": round(float(evolution_ca), 1),
            "panier_moyen": panier_moyen,
            "tickets": total_tickets,
            "ca_packs_percent": round(float(part_ca_packs), 1),
            "masse_salariale": total_masse_salariale,
            "ca_net": ca_net_salon,
            "total_depenses_globales": total_depenses_globales,
            "taux_effort": round(float(taux_effort), 1),
        },
        "stats_employes": stats_employes,
        "top_services": top_services,
        
        # Données graphiques réalignées et sans coupures artificielles
        "chart_days": labels_jours,
        "chart_amounts": donnees_ca,
        
        # Modes de paiement d'origine
        "paiement_labels": [p['mode_paiement'] for p in paiement_modes],
        "paiement_values": [p['total'] for p in paiement_modes],
        
        # Variables de filtres pour tes boucles de sélecteurs HTML
        "months": [(i, datetime.date(2000, i, 1).strftime("%B")) for i in range(1, 13)],
        "years": range(today.year - 1, today.year + 1),
    }

    return render(request, "rapports/global.html", context)




@employe_required
def rapport_coiffeur_detail(request, employe_id):
    # --- 🔐 SÉCURITÉ : AUTORISER GÉRANT, MANAGER ET ADMIN POUR TOUT LE MONDE ---
    est_encadrement = (
        request.user.is_superuser or 
        request.user.groups.filter(name__in=['Gérant', 'Manager']).exists()
    )
    
    if not est_encadrement:
        # Si ce n'est ni un Gérant ni un Manager, c'est un simple coiffeur
        profil_connecte = getattr(request.user, 'employe', None)
        
        # Sécurité : Le coiffeur ne peut voir QUE son propre ID
        if not profil_connecte or profil_connecte.id != int(employe_id):
            raise PermissionDenied("Accès refusé : Vous ne pouvez consulter que vos propres performances.")

    # --- SUITE DU CODE DE TA VUE ---
    employe = get_object_or_404(Employe, pk=employe_id)
    today = date.today()

    # 1. PÉRIODE
    selected_month = int(request.GET.get("month", today.month))
    selected_year = int(request.GET.get("year", today.year))

    month_start = date(selected_year, selected_month, 1)
    month_end = date(selected_year, selected_month, monthrange(selected_year, selected_month)[1])

    # 2. KPI INDIVIDUELS
    paiements = PaiementEmploye.objects.filter(
        employe=employe,
        date_paiement__date__range=[month_start, month_end]
    )

    ca_emp = paiements.aggregate(total=Sum("total_services"))["total"] or 0
    bonus = employe.calculer_bonus(ca_emp)
    total_revenu = float(employe.salaire_base) + bonus

    # --- LOGIQUE PALIERS ---
    p1_ca = float(employe.palier_1_ca or 0)
    p2_ca = float(employe.palier_2_ca or 0)
    ca = float(ca_emp)
    
    reste_p1 = max(0, p1_ca - ca)
    reste_p2 = max(0, p2_ca - ca)

    if ca < p1_ca:
        montant_manquant, objective_nom = reste_p1, "Palier 1"
    elif ca < p2_ca:
        montant_manquant, objective_nom = reste_p2, "Palier 2"
    else:
        montant_manquant, objective_nom = 0, "Maximum"

    # --- PROGRESSION VISUELLE ---
    if ca < p1_ca:
        progression_visuelle = (ca / p1_ca * 100) if p1_ca > 0 else 0
    elif ca < p2_ca and p2_ca > p1_ca:
        progression_visuelle = ((ca - p1_ca) / (p2_ca - p1_ca) * 100)
    else:
        progression_visuelle = 100

    # 3. ÉVOLUTION 6 MOIS
    evolution_list = []
    date_debut_six_mois = month_start - relativedelta(months=5)
    
    stats_globales_evolution = PaiementEmploye.objects.filter(
        date_paiement__date__range=[date_debut_six_mois, month_end]
    ).values('date_paiement__date__year', 'date_paiement__date__month', 'employe').annotate(
        total_ca=Sum('total_services')
    )

    for i in range(5, -1, -1):
        d = month_start - relativedelta(months=i)
        
        ca_mensuel_emp = sum(x['total_ca'] for x in stats_globales_evolution 
                             if x['date_paiement__date__month'] == d.month 
                             and x['date_paiement__date__year'] == d.year 
                             and x['employe'] == employe.id)
        
        ca_tous = [x['total_ca'] for x in stats_globales_evolution 
                   if x['date_paiement__date__month'] == d.month 
                   and x['date_paiement__date__year'] == d.year]
        
        moy_salon = sum(ca_tous) / len(ca_tous) if ca_tous else 0

        evolution_list.append({
            "mois": d.strftime("%b"),
            "employe": float(ca_mensuel_emp),
            "moyenne": float(moy_salon)
        })

    # 4. POSITION DANS LE SALON
    classement_tous = PaiementEmploye.objects.filter(
        date_paiement__date__range=[month_start, month_end]
    ).values("employe").annotate(total_ca=Sum("total_services")).order_by("-total_ca")
    
    position = next((i for i, x in enumerate(classement_tous, 1) if x['employe'] == employe.id), 0)

    # 5. SERVICES FAVORIS
    services_stats = paiements.values("services__nom", "provenance_pack__nom").annotate(
        total=Sum("total_services"), count=Count("services")
    ).order_by("-total")

    context = {
        "employe": employe,
        "stats": {
            "chiffre_affaires": ca_emp,
            "bonus_calcule": bonus,
            "total_revenu_employe": total_revenu,
            "nb_paiements": paiements.count(),
            "reste_p1": reste_p1,
            "reste_p2": reste_p2,
            "montant_manquant": montant_manquant,
        },
        "position": position,
        "progression_visuelle": min(int(progression_visuelle), 100),
        "p1_ca": p1_ca,
        "p2_ca": p2_ca,
        "objectif_nom": objective_nom,
        "services_stats": services_stats,
        "evolution_json": json.dumps(evolution_list),
        "selected_month": selected_month,
        "selected_year": selected_year,
        "months": [(i, date(2000, i, 1).strftime("%B")) for i in range(1, 13)],
        "years": range(today.year - 3, today.year + 1),
        "est_gerant": est_encadrement, # Devient True pour Gérant ET Manager
    }

    return render(request, "rapports/coiffeur_detail.html", context)







from decimal import Decimal
import datetime
from calendar import monthrange
from django.utils import timezone
from django.db.models import Sum, Count, Q, F
# Importe tes modèles ici si nécessaire


def executer_consolidation_belr(annee, mois):
    """
    VERSION CORRIGÉE - ALIGNEMENT STRICT SUR LE RAPPORT GLOBAL.
    Calcule et fige les données en utilisant la formule comptable exacte des stocks.
    """
    aujourd_hui = timezone.now().date()
    month_start = datetime.date(annee, mois, 1)
    _, last_day = monthrange(annee, mois)
    month_end = datetime.date(annee, mois, last_day)

    if mois == 12:
        month_suiv, year_suiv = 1, annee + 1
    else:
        month_suiv, year_suiv = mois + 1, annee

    datetime_start = timezone.make_aware(timezone.datetime(annee, mois, 1, 0, 0, 0))
    datetime_end = timezone.make_aware(timezone.datetime(annee, mois, last_day, 23, 59, 59))

    est_mois_actuel_ou_futur = (annee > aujourd_hui.year) or (annee == aujourd_hui.year and mois >= aujourd_hui.month)

    # 1. CHIFFRE D'AFFAIRES GLOBAL
    metrics_recus = RecuClient.objects.filter(
        date__date__range=[month_start, month_end],
        demande_suppression=False
    ).aggregate(
        total_ca=Sum("total_global"),
        total_tickets=Count("id")
    )
    ca_global = metrics_recus["total_ca"] or Decimal('0.00')
    total_tickets = metrics_recus["total_tickets"] or 0

    # 2. MASSE SALARIALE SÉCURISÉE
    stats_query = PaiementEmploye.objects.filter(
        date_paiement__date__range=[month_start, month_end]
    ).values('employe').annotate(ca_genere=Sum('total_services'))
    stats_map = {item['employe']: item for item in stats_query}

    employes_du_mois = Employe.objects.filter(
        Q(id__in=stats_map.keys()) | Q(actif=True)
    ).distinct().select_related('user').only(
        'id', 'user_id', 'salaire_base', 'palier_1_ca', 'palier_1_percent', 'palier_2_ca', 'palier_2_percent'
    )

    snapshots_existants = {
        s.employe_id: s for s in PerformanceMensuelleSnapshot.objects.filter(mois=mois, annee=annee)
    }

    total_masse_salariale = Decimal('0.00')
    snapshots_a_creer = []
    snapshots_a_mettre_a_jour = []

    for emp in employes_du_mois:
        data = stats_map.get(emp.id, {'ca_genere': 0})
        ca_emp = Decimal(str(data['ca_genere'] or 0))
        snapshot_salaire = snapshots_existants.get(emp.id)
        
        if est_mois_actuel_ou_futur:
            if snapshot_salaire:
                snapshot_salaire.salaire_base_historique = emp.salaire_base or Decimal('0.00')
                snapshot_salaire.palier_1_ca_historique = emp.palier_1_ca or Decimal('0.00')
                snapshot_salaire.palier_1_percent_historique = emp.palier_1_percent or Decimal('0.00')
                snapshot_salaire.palier_2_ca_historique = emp.palier_2_ca or Decimal('0.00')
                snapshot_salaire.palier_2_percent_historique = emp.palier_2_percent or Decimal('0.00')
                snapshots_a_mettre_a_jour.append(snapshot_salaire)
            else:
                snapshot_salaire = PerformanceMensuelleSnapshot(
                    employe=emp, mois=mois, annee=annee,
                    salaire_base_historique=emp.salaire_base or Decimal('0.00'),
                    palier_1_ca_historique=emp.palier_1_ca or Decimal('0.00'),
                    palier_1_percent_historique=emp.palier_1_percent or Decimal('0.00'),
                    palier_2_ca_historique=emp.palier_2_ca or Decimal('0.00'),
                    palier_2_percent_historique=emp.palier_2_percent or Decimal('0.00')
                )
                snapshots_a_creer.append(snapshot_salaire)
        else:
            if not snapshot_salaire:
                vieux_paiement = PaiementEmploye.objects.filter(
                    employe=emp, date_paiement__date__range=[month_start, month_end]
                ).first()
                salaire_recupere = (vieux_paiement.salaire_base_historique if vieux_paiement and hasattr(vieux_paiement, 'salaire_base_historique') else emp.salaire_base) or Decimal('0.00')
                
                snapshot_salaire = PerformanceMensuelleSnapshot(
                    employe=emp, mois=mois, annee=annee,
                    salaire_base_historique=salaire_recupere,
                    palier_1_ca_historique=emp.palier_1_ca or Decimal('0.00'),
                    palier_1_percent_historique=emp.palier_1_percent or Decimal('0.00'),
                    palier_2_ca_historique=emp.palier_2_ca or Decimal('0.00'),
                    palier_2_percent_historique=emp.palier_2_percent or Decimal('0.00')
                )
                snapshots_a_creer.append(snapshot_salaire)

        bonus = Decimal(str(emp.calculer_bonus(
            ca_mensuel=ca_emp,
            p1_ca=snapshot_salaire.palier_1_ca_historique,
            p1_pct=snapshot_salaire.palier_1_percent_historique,
            p2_ca=snapshot_salaire.palier_2_ca_historique,
            p2_pct=snapshot_salaire.palier_2_percent_historique
        )))

        salaire_base_historique = snapshot_salaire.salaire_base_historique if (ca_global > 0 or ca_emp > 0) else Decimal('0.00')
        total_masse_salariale += (salaire_base_historique + bonus)

    if snapshots_a_creer:
        PerformanceMensuelleSnapshot.objects.bulk_create(snapshots_a_creer)
    if snapshots_a_mettre_a_jour:
        PerformanceMensuelleSnapshot.objects.bulk_update(
            snapshots_a_mettre_a_jour, 
            ['salaire_base_historique', 'palier_1_ca_historique', 'palier_1_percent_historique', 'palier_2_ca_historique', 'palier_2_percent_historique']
        )

    # 3. COÛT LOGISTIQUE DES STOCKS (RECOPIÉ STRICTEMENT DE RAPPORT GLOBAL)
    snapshots_mois = {s.produit_id: s for s in StockMensuelSnapshot.objects.filter(mois=mois, annee=annee)}
    snapshots_mois_suiv = {s.produit_id: s for s in StockMensuelSnapshot.objects.filter(mois=month_suiv, annee=year_suiv)}
    
    entrees_mois = {
        item['produit_id']: item['total'] for item in MouvementStock.objects.filter(
            type_mouvement='ENTREE', date_mouvement__range=[datetime_start, datetime_end]
        ).values('produit_id').annotate(total=Sum('quantite'))
    }

    total_cout_produits = Decimal('0.00')
    tous_les_produits = Produit.objects.filter(actif=True)

    for p in tous_les_produits:
        pamp = p.prix_achat_moyen or Decimal('0.00')
        snap = snapshots_mois.get(p.id)
        entrees = entrees_mois.get(p.id, Decimal('0.00'))
        
        stock_initial = snap.quantite_initiale_reelle if snap else (p.quantite_stock if (mois == aujourd_hui.month and annee == aujourd_hui.year) else Decimal('0.00'))
        
        if mois == aujourd_hui.month and annee == aujourd_hui.year:
            stock_final_reel = p.quantite_stock
        else:
            snap_suiv = snapshots_mois_suiv.get(p.id)
            stock_final_reel = snap_suiv.quantite_initiale_reelle if snap_suiv else (stock_initial + entrees)

        quantite_consommee_reelle = (stock_initial + entrees) - stock_final_reel
        if quantite_consommee_reelle < 0: 
            quantite_consommee_reelle = Decimal('0.00')
            
        total_cout_produits += (quantite_consommee_reelle * pamp)

    # 4. CHARGES D'EXPLOITATION NETTES
    total_charges_exploitation = PaiementCharge.objects.filter(
        date_paiement__range=[month_start, month_end]
    ).exclude(charge__type_charge='SALAIRE_FIXE').aggregate(total=Sum('montant_verse'))['total'] or Decimal('0.00')

    # TOTAL FINANCIER CONSOLIDÉ
    total_couts_globaux = total_masse_salariale + total_cout_produits + total_charges_exploitation

    # Enregistrement final
    rapport, _ = RapportMensuelConsolide.objects.update_or_create(
        annee=annee, mois=mois,
        defaults={
            'chiffre_affaires': ca_global,
            'couts_generaux': total_couts_globaux,
            'nombre_fiches_traitees': total_tickets,
        }
    )
    return rapport





@login_required
def rapport_annuel_view(request):
    """
    VERSION NETTOYÉE ET ALIGNÉE.
    Recalcule l'intégralité des mois affichés pour garantir un coût annuel exact.
    """
    aujourd_hui = timezone.now().date()
    annee_en_cours = aujourd_hui.year
    annee_precedente = annee_en_cours - 1
    mois_en_cours = aujourd_hui.month

    noms_mois = [
        "Janvier", "Février", "Mars", "Avril", "Mai", "Juin", 
        "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"
    ]

    # 🔥 CORRECTION DE FOND : Forcer la reconsolidation automatique de tous les mois pour écraser les anciennes valeurs fausses
    for m in range(1, 13):
        executer_consolidation_belr(annee_precedente, m)
        if m <= mois_en_cours:
            executer_consolidation_belr(annee_en_cours, m)

    # Lecture des rapports maintenant corrigés et figés
    rapports_db = RapportMensuelConsolide.objects.filter(
        annee__in=[annee_en_cours, annee_precedente]
    ).only('annee', 'mois', 'chiffre_affaires', 'couts_generaux')

    donnees_n = {}
    donnees_n_minus_1 = {}
    for r in rapports_db:
        if r.annee == annee_en_cours:
            donnees_n[r.mois] = r
        else:
            donnees_n_minus_1[r.mois] = r

    ca_chart_annee_en_cours = [0.0] * 12
    ca_chart_annee_precedente = [0.0] * 12
    couts_chart_annee_en_cours = [0.0] * 12
    tableau_comparatif = []

    total_ca_n = Decimal('0.00')
    total_couts_n = Decimal('0.00')
    total_ca_n_1_isoperimetre = Decimal('0.00')
    total_couts_n_1_isoperimetre = Decimal('0.00')

    for i in range(1, 13):
        index_mois = i - 1
        rapport_n = donnees_n.get(i)
        rapport_n_1 = donnees_n_minus_1.get(i)

        ca_n = rapport_n.chiffre_affaires if rapport_n else Decimal('0.00')
        couts_n = rapport_n.couts_generaux if rapport_n else Decimal('0.00')
        
        ca_n_1 = rapport_n_1.chiffre_affaires if rapport_n_1 else Decimal('0.00')
        couts_n_1 = rapport_n_1.couts_generaux if rapport_n_1 else Decimal('0.00')

        # Alimentation graphiques
        ca_chart_annee_en_cours[index_mois] = float(ca_n)
        couts_chart_annee_en_cours[index_mois] = float(couts_n)
        ca_chart_annee_precedente[index_mois] = float(ca_n_1)

        total_ca_n += ca_n
        total_couts_n += couts_n

        if ca_n > 0 or couts_n > 0:
            total_ca_n_1_isoperimetre += ca_n_1
            total_couts_n_1_isoperimetre += couts_n_1

        # Calculs locaux basés sur les données réelles
        evo_ca_pct = round(((ca_n - ca_n_1) / ca_n_1 * 100), 2) if ca_n_1 > 0 else 0.0
        evo_couts_pct = round(((couts_n - couts_n_1) / couts_n_1 * 100), 2) if couts_n_1 > 0 else 0.0

        tableau_comparatif.append({
            'numero_mois': i,
            'nom_mois': noms_mois[index_mois],
            'ca_n': ca_n,
            'ca_n_1': ca_n_1,
            'couts_n': couts_n,
            'couts_n_1': couts_n_1,
            'evo_ca_pct': float(evo_ca_pct),
            'evo_couts_pct': float(evo_couts_pct),
            'effet_ciseau': float(evo_ca_pct - evo_couts_pct),
            'benefice_net': (ca_n - couts_n)
        })

    # Indicateurs globaux annuels
    evolution_ca_annuel_pct = round(((total_ca_n - total_ca_n_1_isoperimetre) / total_ca_n_1_isoperimetre) * 100, 2) if total_ca_n_1_isoperimetre > 0 else 0.0
    evolution_couts_annuel_pct = round(((total_couts_n - total_couts_n_1_isoperimetre) / total_couts_n_1_isoperimetre) * 100, 2) if total_couts_n_1_isoperimetre > 0 else 0.0
    effet_ciseau_global = round(float(evolution_ca_annuel_pct) - float(evolution_couts_annuel_pct), 2)

    context = {
        'annee_en_cours': annee_en_cours,
        'annee_precedente': annee_precedente,
        'tableau_comparatif': tableau_comparatif,
        'total_ca_n': total_ca_n,
        'total_couts_n': total_couts_n,
        'rentabilite_globale': total_ca_n - total_couts_n,
        'evolution_ca_annuel_pct': evolution_ca_annuel_pct,
        'evolution_couts_annuel_pct': evolution_couts_annuel_pct,
        'effet_ciseau_global': effet_ciseau_global,
        'labels_mois_json': json.dumps(noms_mois),
        'ca_chart_annee_en_cours_json': json.dumps(ca_chart_annee_en_cours),
        'ca_chart_annee_precedente_json': json.dumps(ca_chart_annee_precedente),
        'couts_chart_annee_en_cours_json': json.dumps(couts_chart_annee_en_cours),
    }
    return render(request, 'rapports/rapport_annuel.html', context)