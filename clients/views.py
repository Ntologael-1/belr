
# # Remplacer par votre import exact (ex: @login_required ou votre décorateur personnalisé)
# ==========================================
# 1. Standard Library Imports
# ==========================================
import datetime
from datetime import date, datetime, timedelta
from calendar import monthrange
from collections import defaultdict
from decimal import Decimal
import json
import math
import statistics

# ==========================================
# 2. Django Core & Third-Party Imports
# ==========================================
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db.models import (
    Avg, Case, CharField, Count, DecimalField, ExpressionWrapper, F, 
    fields, IntegerField, Max, Min, OuterRef, Q, Subquery, Sum, Value, When
)
from django.db.models.functions import (
    Coalesce, Concat, ExtractDay, ExtractHour, ExtractMonth, 
    ExtractWeekDay, ExtractYear, TruncDate
)
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

# ==========================================
# 3. Local Apps Imports (Ajuste selon ton projet)
# ==========================================
from authentification.decorator import employe_required, gerant_only, manager_required
from employes.models import Employe
from gestion.models import CategorieService, Service
from inventaire.models import ConsommableService
from rendezvous.models import PaiementEmploye, RecuClient

# Si ce fichier d'importation est dans le même dossier que ces modèles/formulaires :
from .forms import ClientForm
from .models import Client









@manager_required
def client_create(request):
    """
    DASHBOARD BI PREMIUM - BEL'R (VERSION LIGHTNING SPEED ⚡)
    Optimisation : Agrégations groupées, suppression des requêtes N+1 et formatage HTML natif.
    """
   # =========================================================
    # 1. PARAMÈTRES / FILTRES & GENERATION DES PLAGES DE DATES
    # =========================================================
    import datetime

    today = timezone.now() # Date "aware" avec le bon fuseau horaire
    try:
        selected_month = int(request.GET.get('month', today.month))
        selected_year = int(request.GET.get('year', today.year))
    except (TypeError, ValueError):
        selected_month, selected_year = today.month, today.year

    if not (1 <= selected_month <= 12): 
        selected_month = today.month
    
    prev_month, prev_year = (12, selected_year - 1) if selected_month == 1 else (selected_month - 1, selected_year)

    # Construction des bornes du mois sélectionné (dates naïves d'abord)
    start_date_naive = datetime.datetime(selected_year, selected_month, 1, 0, 0, 0)
    if selected_month == 12:
        end_date_naive = datetime.datetime(selected_year + 1, 1, 1, 0, 0, 0)
    else:
        end_date_naive = datetime.datetime(selected_year, selected_month + 1, 1, 0, 0, 0)

    # Bornes du mois précédent
    prev_start_date_naive = datetime.datetime(prev_year, prev_month, 1, 0, 0, 0)
    if prev_month == 12:
        prev_end_date_naive = datetime.datetime(prev_year + 1, 1, 1, 0, 0, 0)
    else:
        prev_end_date_naive = datetime.datetime(prev_year, prev_month + 1, 1, 0, 0, 0)

    # RENDRE LES DATES "AWARE" (Résout le bug du 0 partout 🚀)
    # On utilise gte (supérieur ou égal) et lt (strictement inférieur) pour éviter les décalages de secondes
    start_date = timezone.make_aware(start_date_naive)
    end_date = timezone.make_aware(end_date_naive)
    
    prev_start_date = timezone.make_aware(prev_start_date_naive)
    prev_end_date = timezone.make_aware(prev_end_date_naive)

    # =========================================================
    # 2. QUERYSETS DE BASE (Filtrage ultra-précis par plage)
    # =========================================================
    current_qs = PaiementEmploye.objects.filter(
        date_paiement__gte=start_date,
        date_paiement__lt=end_date
    ).select_related('employe__user')
    
    previous_qs = PaiementEmploye.objects.filter(
        date_paiement__gte=prev_start_date,
        date_paiement__lt=prev_end_date
    )
    # =========================================================
    # 3. HELPERS DE CALCUL
    # =========================================================
    def safe_d(v): return Decimal(str(v)) if v is not None else Decimal('0')
    
    def pct_change(curr, prev):
        curr, prev = safe_d(curr), safe_d(prev)
        if prev > 0: return ((curr - prev) / prev) * 100
        return 100 if curr > 0 else 0

    # =========================================================
    # 4. KPI GLOBAUX
    # =========================================================
    stats = current_qs.aggregate(
        ca_total=Sum('total_services'),
        ca_packs=Sum('total_services', filter=Q(provenance_pack__isnull=False)),
        ca_simples=Sum('total_services', filter=Q(provenance_pack__isnull=True)),
        nb_simples=Count('id', filter=Q(provenance_pack__isnull=True), distinct=True)
    )

    p_pack_qs = current_qs.filter(provenance_pack__isnull=False)

    stats_packs_volume = (
        p_pack_qs
        .values('pack_instance_id')
        .annotate(qte_par_instance=Avg('quantite')) 
        .aggregate(total_packs=Sum('qte_par_instance'))
    )

    nb_packs = stats_packs_volume['total_packs'] or 0

    ca_total = safe_d(stats['ca_total'])
    ca_packs = safe_d(stats['ca_packs'])
    ca_simples = safe_d(stats['ca_simples'])
    nb_simples = stats['nb_simples'] or 0
    nb_total = nb_packs + nb_simples
    # === ANCIEN CODE QUI PLANTAIT ===
    # pm_global = ca_total / nb_total if nb_total > 0 else 0
    # pm_pack = ca_packs / nb_packs if nb_packs > 0 else 0
    # pm_simple = ca_simples / nb_simples if nb_simples > 0 else 0

    # === NOUVEAU CODE SÉCURISÉ 🚀 ===
    # On force le diviseur à être un Decimal pour correspondre au CA
    pm_global = ca_total / safe_d(nb_total) if safe_d(nb_total) > 0 else Decimal('0')
    pm_pack = ca_packs / safe_d(nb_packs) if safe_d(nb_packs) > 0 else Decimal('0')
    pm_simple = ca_simples / safe_d(nb_simples) if safe_d(nb_simples) > 0 else Decimal('0')
    
    uplift = ((pm_pack - pm_simple) / pm_simple * 100) if pm_simple > 0 else 0
    part_ca_packs = (ca_packs / ca_total * 100) if ca_total > 0 else 0

    prev_stats = previous_qs.aggregate(
        ca_packs=Sum('total_services', filter=Q(provenance_pack__isnull=False))
    )

    # =========================================================
    # 5. TOP SERVICES SIMPLES
    # =========================================================
    top_services_simples = (
        Service.objects.filter(
            paiements__date_paiement__month=selected_month,
            paiements__date_paiement__year=selected_year,
            est_un_pack=False,
            paiements__provenance_pack__isnull=True
        )
        .annotate(
            nb_ventes=Count('paiements', distinct=True),
            ca_reel=Sum('paiements__total_services')
        )
        .order_by('-ca_reel')[:5]
    )

    # =========================================================
    # 6. PARETO 80/20 & TOP PACKS (Optimisé sans requête N+1 🚀)
    # =========================================================
    # On récupère le nombre de services inclus par pack en une SEULE requête SQL groupée
    configs = dict(
        Service.objects.filter(est_un_pack=True)
        .annotate(nb_inclus=Count('services_inclus'))
        .values_list('id', 'nb_inclus')
    )

    all_packs_qs = (
        Service.objects.filter(est_un_pack=True, actif=True)
        .annotate(
            ca_p=Sum('contributions_pack__total_services', 
                    filter=Q(contributions_pack__date_paiement__month=selected_month, 
                             contributions_pack__date_paiement__year=selected_year)),
            nb_lignes=Count('contributions_pack', distinct=True)
        )
        .filter(ca_p__gt=0).order_by('-ca_p')
    )

    pareto_data = []
    cumul_ca = Decimal('0')
    pareto_80_count = 0
    for i, pack in enumerate(all_packs_qs, 1):
        p_ca = safe_d(pack.ca_p)
        cumul_ca += p_ca
        pct_cumul = (cumul_ca / ca_packs * 100) if ca_packs > 0 else 0
        if pareto_80_count == 0 and pct_cumul >= 80: 
            pareto_80_count = i
        
        conf = configs.get(pack.id, 1) or 1
        vrai_nb = math.ceil(pack.nb_lignes / conf)

        pareto_data.append({
            'rang': i, 'nom': pack.nom, 'ca': float(p_ca), 
            'nb_ventes': vrai_nb, 'percent_cumul': round(float(pct_cumul), 2)
        })

    # =========================================================
    # 7. ANALYSES TEMPORELLES
    # =========================================================
    perf_horaire = (current_qs.annotate(h=ExtractHour('date_paiement'))
                    .values('h').annotate(ca=Sum('total_services'))
                    .order_by('h'))
    
    best_hour_data = max(perf_horaire, key=lambda x: x['ca'], default={'h': None, 'ca': 0})

    # =========================================================
    # 8. TOP VENDEURS (Correction du Nom Concatené)
    # =========================================================
    def get_top_vendeurs(qs):
        raw_vendeurs = (qs.values(
            'employe__user__first_name', 
            'employe__user__last_name', 
            'employe__user__username'
        ).annotate(
            ca=Sum('total_services'), 
            nb=Count('id')
        ).order_by('-ca')[:5])
        
        # Reconstruction propre d'un dictionnaire pour le template HTML
        vendeurs_formates = []
        for v in raw_vendeurs:
            first = v['employe__user__first_name'] or ""
            last = v['employe__user__last_name'] or ""
            vendeurs_formates.append({
                'nom': f"{first} {last}".strip() or v['employe__user__username'],
                'nb': v['nb'],
                'ca': float(safe_d(v['ca']))
            })
        return vendeurs_formates

    top_vendeurs_packs = get_top_vendeurs(current_qs.filter(provenance_pack__isnull=False))

    # =========================================================
    # 9. ALERTES & ARRHÈRES CONTEXTE
    # =========================================================
    business_alerts = []
    if ca_packs == 0:
        business_alerts.append({'type': 'danger', 'title': "Alerte Ventes", 'message': "Aucun pack vendu ce mois-ci."})
    if uplift > 0:
        business_alerts.append({'type': 'success', 'title': "Performance", 'message': f"Les packs boostent le panier de {round(uplift, 1)}%."})

    pareto_labels = [item['nom'] for item in pareto_data]
    pareto_ca_values = [item['ca'] for item in pareto_data]
    pareto_cumul_values = [item['percent_cumul'] for item in pareto_data]

    # Extraction des années disponibles pour éviter le crash dans le select
    years_range = list(range(today.year - 2, today.year + 1))

    context = {
        'selected_month': selected_month, 'selected_year': selected_year,
        'available_years': years_range,
        'ca_total': float(ca_total), 'nb_total': nb_total, 'panier_moyen_global': float(pm_global),
        'ca_packs': float(ca_packs), 'nb_packs': nb_packs, 'panier_moyen_pack': float(pm_pack),
        'ca_simples': float(ca_simples), 'nb_simples': nb_simples, 'panier_moyen_simple': float(pm_simple),
        'uplift': round(float(uplift), 2),
        'part_ca_packs': round(float(part_ca_packs), 2),
        'evolution_ca_packs': round(float(pct_change(ca_packs, prev_stats['ca_packs'])), 2),
        
        'pareto_labels': json.dumps(pareto_labels),
        'pareto_ca_values': json.dumps(pareto_ca_values),
        'pareto_cumul_values': json.dumps(pareto_cumul_values),
        'pareto_results': pareto_data,
        'pareto_80_count': pareto_80_count,
        'top_packs': pareto_data[:5],
        'top_vendeurs': top_vendeurs_packs,
        'top_services_simples': top_services_simples,
        
        'mix_ca': json.dumps([float(ca_packs), float(ca_simples)]),
        'labels_horaire': json.dumps([f"{i['h']}h" for i in perf_horaire]),
        'data_horaire_ca': json.dumps([float(i['ca']) for i in perf_horaire]),
        
        'business_alerts': business_alerts,
        'best_hour': f"{best_hour_data['h']}h00" if best_hour_data['h'] is not None else None,
        'month_names': [(1, "Janvier"), (2, "Février"), (3, "Mars"), (4, "Avril"), (5, "Mai"), (6, "Juin"), 
                        (7, "Juillet"), (8, "Août"), (9, "Septembre"), (10, "Octobre"), (11, "Novembre"), (12, "Décembre")],
    }

    return render(request, 'clients/form.html', context)






import math



#client_edit



#GRAPH RAPPORT
@gerant_only
def historique_create(request):
    """
    DASHBOARD GRAPHIQUE BUSINESS INTELLIGENCE - BEL'R
    Page dédiée aux graphiques les plus importants (sans courbe d'évolution)
    """

    # =========================================================
    # 1) PERIODE SELECTIONNEE
    # =========================================================
    today = timezone.now().date()

    selected_month = int(request.GET.get("month", today.month))
    selected_year = int(request.GET.get("year", today.year))

    # Sécurisation simple
    if selected_month < 1 or selected_month > 12:
        selected_month = today.month

    month_start = date(selected_year, selected_month, 1)
    _, last_day = monthrange(selected_year, selected_month)
    month_end = date(selected_year, selected_month, last_day)

    # =========================================================
    # 2) QUERYSETS DE BASE
    # =========================================================
    paiements = (
        PaiementEmploye.objects
        .filter(date_paiement__date__range=[month_start, month_end])
        .select_related('employe', 'services', 'services__categorie')
    )

    recus = RecuClient.objects.filter(date__date__range=[month_start, month_end])

    # =========================================================
    # 3) KPI GLOBAUX (UTILISES DANS LES CARTES + CENTRES DONUT)
    # =========================================================
    ca_total = paiements.aggregate(total=Sum('total_services'))['total'] or 0
    ca_total = float(ca_total)

    total_paiements = paiements.count()
    total_recus = recus.count()

    panier_moyen_global = round((ca_total / total_paiements), 2) if total_paiements > 0 else 0

    # =========================================================
    # 4) GRAPH 1 - AFFLUENCE HORAIRE + CA HORAIRE
    # =========================================================
    hourly_stats = list(
        paiements.annotate(hour=ExtractHour('date_paiement'))
        .values('hour')
        .annotate(
            count=Count('id'),
            total=Sum('total_services')
        )
        .order_by('hour')
    )

    labels_hour = [f"{row['hour']}h" for row in hourly_stats if row['hour'] is not None]
    values_hour_count = [row['count'] for row in hourly_stats if row['hour'] is not None]
    values_hour_ca = [float(row['total'] or 0) for row in hourly_stats if row['hour'] is not None]

    peak_hour = None
    peak_hour_count = 0
    if hourly_stats:
        valid_hours = [row for row in hourly_stats if row['hour'] is not None]
        if valid_hours:
            best_hour = max(valid_hours, key=lambda x: x['count'])
            peak_hour = f"{best_hour['hour']}h"
            peak_hour_count = best_hour['count']

   # =========================================================
    # 5) GRAPH 2 - DONUT REPARTITION PAR CATEGORIE (CA) - VERSION FIABLE
    # =========================================================
    # On utilise Coalesce pour être SUR qu'aucune catégorie n'est NULL
    category_data = list(
        paiements.annotate(
            nom_nettoyé=Coalesce('services__categorie__nom', Value("Sans catégorie"))
        )
        .values('nom_nettoyé')
        .annotate(
            total=Sum('total_services'),
            count=Count('id')
        )
        .order_by('-total') # Tri décroissant par CA
    )

    # ON GÉNÈRE LES LISTES EN UNE SEULE FOIS POUR GARDER L'ORDRE
    labels_cat = [row['nom_nettoyé'] for row in category_data]
    values_cat = [float(row['total'] or 0) for row in category_data]
    category_counts = [row['count'] for row in category_data]
    
    # Calcul des pourcentages basé sur les valeurs déjà extraites

    category_percentages = [
        round((v / ca_total * 100), 2) if ca_total > 0 else 0 
        for v in values_cat
    ]



    categories_details = []
    for i in range(len(labels_cat)):
        categories_details.append({
            'label': labels_cat[i],
            'value': values_cat[i],
            'percentage': category_percentages[i]
        })

    top_category_name = labels_cat[0] if labels_cat else None

    # =========================================================
    # 6) GRAPH 3 - TOP SERVICES LES PLUS RENTABLES (CA)
    # =========================================================
    top_services_ca_qs = list(
        paiements.values('services__nom', 'services__couleur', 'services__code')
        .annotate(
            total=Sum('total_services'),
            count=Count('id')
        )
        .order_by('-total')[:8]
    )

    labels_services_ca = []
    values_services_ca = []
    counts_services_ca = []
    colors_services_ca = []

    for row in top_services_ca_qs:
        labels_services_ca.append(row['services__nom'] or "Service inconnu")
        values_services_ca.append(float(row['total'] or 0))
        counts_services_ca.append(row['count'] or 0)
        colors_services_ca.append(row['services__couleur'] or "#007bff")

    top_service_name = labels_services_ca[0] if labels_services_ca else None

    # =========================================================
    # 7) GRAPH 4 - TOP SERVICES LES PLUS VENDUS (VOLUME)
    # =========================================================
    top_services_count_qs = list(
        paiements.values('services__nom', 'services__couleur', 'services__code')
        .annotate(
            count=Count('id'),
            total=Sum('total_services')
        )
        .order_by('-count', '-total')[:8]
    )

    labels_services_count = []
    values_services_count = []
    values_services_count_ca = []
    colors_services_count = []

    for row in top_services_count_qs:
        labels_services_count.append(row['services__nom'] or "Service inconnu")
        values_services_count.append(row['count'] or 0)
        values_services_count_ca.append(float(row['total'] or 0))
        colors_services_count.append(row['services__couleur'] or "#20c997")

    # =========================================================
    # 8) GRAPH 5 - PACKS VS SERVICES SIMPLES - RÉPARÉ
    # =========================================================
    
    p_pack_qs = paiements.filter(provenance_pack__isnull=False)
    
    stats_packs_volume = (
        p_pack_qs
        .values('pack_instance_id')
        .annotate(qte_par_instance=Avg('quantite')) 
        .aggregate(total_packs=Sum('qte_par_instance'))
    )

    # 2. On agrège le reste (CA et Services simples)
    # Note : pour les services simples, on utilise Sum('quantite') au cas où 
    # un employé vendrait 2 fois le même service sur une ligne.
    packs_stats = paiements.aggregate(
        ca_pack=Sum('total_services', filter=Q(provenance_pack__isnull=False)),
        ca_simple=Sum('total_services', filter=Q(provenance_pack__isnull=True)),
        nb_simple=Sum('quantite', filter=Q(provenance_pack__isnull=True)),
    )

    # 3. Extraction des valeurs
    pack_total = float(packs_stats['ca_pack'] or 0)
    # C'est ici qu'on applique la nouvelle logique de volume
    pack_count = float(stats_packs_volume['total_packs'] or 0)
    
    simple_total = float(packs_stats['ca_simple'] or 0)
    simple_count = float(packs_stats['nb_simple'] or 0)

    # 4. Données pour les graphiques
    labels_pack_split = ["Services simples", "Packs"]
    values_pack_split_count = [simple_count, pack_count]
    values_pack_split_ca = [simple_total, pack_total]

    # Part du CA (en utilisant le ca_total calculé plus haut dans ta vue)
    pack_share_pct = round((pack_total / float(ca_total)) * 100, 2) if ca_total > 0 else 0








    # =========================================================
    # 9) GRAPH 6 & 7 - PERFORMANCE EMPLOYÉS (OPTIMISÉ)
    # =========================================================
    # On récupère tous les employés actifs
    employes = list(
        Employe.objects.filter(actif=True)
        .select_related('user')
    )

    # Une seule grosse requête groupée pour éviter N requêtes
    emp_stats_qs = list(
        paiements.values('employe')
        .annotate(
            ca=Sum('total_services'),
            nb=Count('id')
        )
    )

    # Dictionnaire rapide: employe_id -> stats
    emp_stats_map = {
        row['employe']: {
            'ca': float(row['ca'] or 0),
            'nb': row['nb'] or 0
        }
        for row in emp_stats_qs
    }

    emp_names = []
    emp_ca = []
    emp_cout = []
    emp_profit = []
    emp_panier = []
    emp_rentabilite = []
    emp_bonus = []

    best_employee = None
    best_employee_profit = None
    best_employee_ca = None

    for emp in employes:
        stats = emp_stats_map.get(emp.id, {'ca': 0.0, 'nb': 0})

        ca_emp = float(stats['ca'])
        nb_emp = stats['nb']

        bonus = float(emp.calculer_bonus(ca_emp) or 0)
        salaire_base = float(emp.salaire_base or 0)
        cout_total = salaire_base + bonus

        profit = ca_emp - cout_total

        # IMPORTANT : sécurité division par zéro
        panier_moyen_emp = round((ca_emp / nb_emp), 2) if nb_emp > 0 else 0

        # Taux de rentabilité
        rentabilite = round((profit / ca_emp) * 100, 2) if ca_emp > 0 else 0

        emp_names.append(emp.nom_complet)
        emp_ca.append(round(ca_emp, 2))
        emp_cout.append(round(cout_total, 2))
        emp_profit.append(round(profit, 2))
        emp_panier.append(panier_moyen_emp)
        emp_rentabilite.append(rentabilite)
        emp_bonus.append(round(bonus, 2))

        if best_employee_profit is None or profit > best_employee_profit:
            best_employee_profit = profit
            best_employee = emp.nom_complet
            best_employee_ca = ca_emp

    # =========================================================
    # 10) KPI BONUS - CONCENTRATION DU CA (RISQUE BUSINESS)
    # =========================================================
    top_3_ca = sorted(emp_ca, reverse=True)[:3]
    concentration_top3 = round((sum(top_3_ca) / ca_total) * 100, 2) if ca_total > 0 else 0

    # =========================================================
    # 11) KPI BONUS - SERVICE MOYEN / DIVERSIFICATION
    # =========================================================
    nb_services_distincts = paiements.values('services').distinct().count()

    # =========================================================
    # 12) CONTEXTE FINAL
    # =========================================================
    context = {
        # -------------------------
        # Filtres période
        # -------------------------
        "selected_month": selected_month,
        "selected_year": selected_year,
        "months": [(i, date(2000, i, 1).strftime("%B")) for i in range(1, 13)],

        # -------------------------
        # KPI globaux
        # -------------------------
        "ca_total": ca_total,
        "total_paiements": total_paiements,
        "total_recus": total_recus,
        "panier_moyen_global": panier_moyen_global,
        "peak_hour": peak_hour,
        "peak_hour_count": peak_hour_count,
        "best_employee": best_employee,
        "best_employee_profit": round(best_employee_profit, 2) if best_employee_profit is not None else 0,
        "best_employee_ca": round(best_employee_ca, 2) if best_employee_ca is not None else 0,
        "top_service_name": top_service_name,
        "top_category_name": top_category_name,
        "concentration_top3": concentration_top3,
        "nb_services_distincts": nb_services_distincts,
        "pack_share_pct": pack_share_pct,

        # -------------------------
        # GRAPH 1 - Affluence + CA horaire
        # -------------------------
        "labels_hour": labels_hour,
        "values_hour_count": values_hour_count,
        "values_hour_ca": values_hour_ca,

        # -------------------------
        # GRAPH 2 - Donut catégories
        # -------------------------
        "categories_details": categories_details, 
        "labels_cat": labels_cat,
        "values_cat": values_cat,
        "category_counts": category_counts,
        "category_percentages": category_percentages,

        # -------------------------
        # GRAPH 3 - Top services par CA
        # -------------------------
        "labels_services_ca": labels_services_ca,
        "values_services_ca": values_services_ca,
        "counts_services_ca": counts_services_ca,
        "colors_services_ca": colors_services_ca,

        # -------------------------
        # GRAPH 4 - Top services par volume
        # -------------------------
        "labels_services_count": labels_services_count,
        "values_services_count": values_services_count,
        "values_services_count_ca": values_services_count_ca,
        "colors_services_count": colors_services_count,

        # -------------------------
        # GRAPH 5 - Packs vs simples
        # -------------------------
        "labels_pack_split": labels_pack_split,
        "values_pack_split_count": values_pack_split_count,
        "values_pack_split_ca": values_pack_split_ca,
        "pack_count": pack_count,
        "simple_count": simple_count,
        "pack_total": pack_total,
        "simple_total": simple_total,

        # -------------------------
        # GRAPH 6 - CA / Coût / Profit employés
        # -------------------------
        "emp_names": emp_names,
        "emp_ca": emp_ca,
        "emp_cout": emp_cout,
        "emp_profit": emp_profit,
        "emp_bonus": emp_bonus,

        # -------------------------
        # GRAPH 7 - Panier / Rentabilité employés
        # -------------------------
        "emp_panier": emp_panier,
        "emp_rentabilite": emp_rentabilite,
    }

    return render(request, 'clients/historique_form.html', context)






from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q, Sum, Count, Avg, F

@manager_required
def clients_list(request):
    # 1. Gestion des dates
    selected_month = int(request.GET.get('month', timezone.now().month))
    selected_year = int(request.GET.get('year', timezone.now().year))
    
    # Filtres de base
    filtre_recu = Q(date__month=selected_month, date__year=selected_year)
    filtre_paiement = Q(date_paiement__month=selected_month, date_paiement__year=selected_year)

    # 2. Chiffre d'Affaires Réel
    total_ca = RecuClient.objects.filter(filtre_recu).aggregate(Sum('total_global'))['total_global__sum'] or 0
    
    # --- GESTION DE L'EVOLUTION ---
    if selected_month == 1:
        prev_month = 12
        prev_year = selected_year - 1
    else:
        prev_month = selected_month - 1
        prev_year = selected_year

    last_month_ca = RecuClient.objects.filter(
        date__month=prev_month, 
        date__year=prev_year
    ).aggregate(Sum('total_global'))['total_global__sum'] or 0

    if last_month_ca > 0:
        evolution_ca = round(((total_ca - last_month_ca) / last_month_ca) * 100, 1)
    elif total_ca > 0:
        evolution_ca = 100.0
    else:
        evolution_ca = 0.0
    # ------------------------------

    # 3. Panier Moyen, Tickets ET Médiane
    stats_recus = RecuClient.objects.filter(filtre_recu).aggregate(
        avg_panier=Avg('total_global'),
        count_tickets=Count('id')
    )
    
    panier_moyen = stats_recus['avg_panier'] or 0
    tickets_count = stats_recus['count_tickets'] or 0

    total_prestations = PaiementEmploye.objects.filter(filtre_paiement).count()

    # Calcul de la Médiane
    recus_query = RecuClient.objects.filter(filtre_recu).values_list('total_global', flat=True).order_by('total_global')
    panier_mediane = 0
    if tickets_count > 0:
        if tickets_count % 2 == 1:
            panier_mediane = recus_query[tickets_count // 2]
        else:
            mid1 = recus_query[(tickets_count // 2) - 1]
            mid2 = recus_query[tickets_count // 2]
            panier_mediane = (mid1 + mid2) / 2

    # Calcul des services par ticket
    tickets_count_divider = stats_recus['count_tickets'] or 1
    services_par_client = round(total_prestations / tickets_count_divider, 1)

    # 4. Performance des Prestations (Calcul global initial)
    services_perf_queryset = PaiementEmploye.objects.filter(filtre_paiement).values(
        nom_service=F('services__nom'),
        cat=F('services__categorie__nom'),
        is_pack=F('provenance_pack__nom'),
        prix_unitaire=F('total_services')
    ).annotate(
        nb_prestations=Count('id'),
        ca_genere=Sum('total_services')
    ).order_by('-ca_genere')

    # Convertir en liste pour connaître la longueur et extraire le Top Service
    services_perf_list = list(services_perf_queryset)
    has_results = len(services_perf_list) > 0

    top_service = None
    if has_results:
        top_service = {
            'nom': services_perf_list[0]['nom_service'],
            'ca_genere': services_perf_list[0]['ca_genere']
        }

    # --- APPLICATION DE LA PAGINATION POUR LE TABLEAU DES PRESTATIONS ---
    page = request.GET.get('page', 1)
    paginator = Paginator(services_perf_list, 20)  # 20 lignes de prestations par page

    try:
        services_perf_pagines = paginator.page(page)
    except PageNotAnInteger:
        services_perf_pagines = paginator.page(1)
    except EmptyPage:
        services_perf_pagines = paginator.page(paginator.num_pages)

    # 5. Données pour les Graphiques
    cat_data = PaiementEmploye.objects.filter(filtre_paiement).values('services__categorie__nom').annotate(ca=Sum('total_services'))
    cat_labels = [c['services__categorie__nom'] or "Autre" for c in cat_data]
    cat_data_ca = [float(c['ca']) for c in cat_data]

    heures_raw = RecuClient.objects.filter(filtre_recu).values('date__hour').annotate(ca=Sum('total_global')).order_by('date__hour')
    heures_labels = [f"{h['date__hour']}h" for h in heures_raw]
    heures_data = [float(h['ca']) for h in heures_raw]

    paiement_raw = RecuClient.objects.filter(filtre_recu).values('mode_paiement').annotate(count=Count('id'))
    paiement_labels = [p['mode_paiement'] for p in paiement_raw]
    paiement_data = [p['count'] for p in paiement_raw]

    context = {
        'total_ca': total_ca,
        'evolution_ca': evolution_ca,
        'panier_moyen': panier_moyen,
        'panier_mediane': panier_mediane,
        'services_par_client': services_par_client,
        'top_service': top_service,
        'total_prestations': total_prestations,
        'services_perf': services_perf_pagines,  # Remplacé par l'objet paginé
        'has_results': has_results,              # Indicateur d'état vide
        'cat_labels': cat_labels,
        'cat_data_ca': cat_data_ca,
        'heures_labels': heures_labels,
        'heures_data': heures_data,
        'paiement_labels': paiement_labels,
        'paiement_data': paiement_data,
        'selected_month': selected_month,
        'selected_year': selected_year,
        'months': [(i, timezone.datetime(2000, i, 1).strftime('%B')) for i in range(1, 13)],
        'years': [2025, 2026],
    }
    return render(request, 'clients/list.html', context)






