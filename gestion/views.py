# ==========================================
# 1. Standard Library Imports
# ==========================================
from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
import json
import math
import statistics
import uuid

# ==========================================
# 2. Django Core & Third-Party Imports
# ==========================================
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models, transaction
from django.db.models import (
    Avg, Case, CharField, Count, DecimalField, ExpressionWrapper, F,
    IntegerField, Max, Min, OuterRef, Prefetch, Q, Subquery, Sum, Value, When,
    fields
)
from django.db.models.functions import (
    Coalesce, Concat, ExtractDay, ExtractHour, ExtractMonth,
    ExtractWeekDay, ExtractYear, TruncDate, TruncDay
)
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

# ==========================================
# 3. Local Apps Imports (Modèles, Formulaires, Décorateurs)
# ==========================================
from authentification.decorator import employe_required, gerant_only, manager_required

from clients.models import Client
from employes.models import Employe
from gestion.models import CategorieService, Service
from inventaire.models import ConsommableService
from rendezvous.models import PaiementEmploye, RecuClient

# Imports relatifs (modèles et formuels de l’application courante)
from .forms import ServiceForm
from .models import Parametre, Salon, Service

# Create your views here.



TAGS_SUGGESTIONS = [
    "Homme",
    "Femme",
    "Enfant",
    "Coloration",
    "Coupe",
    "Soin",
    "Brushing",
    "Barbe",
]

COULEURS_PRESETS = [
    "#8A2BE2",
    "#00D4AA",
    "#FF6B8B",
    "#FF9F43",
    "#00CFE8",
    "#28C76F",
    "#EA5455",
    "#1E1E2E",
]








from django.shortcuts import render
from django.contrib.auth.decorators import login_required

@login_required
def accueil(request):
    # La vue a juste besoin de renvoyer le template, 
    # request.user est déjà accessible directement dans le HTML.
    return render(request, 'gestion/accueil.html')




@manager_required
def service_edit(request, pk):
    """Modifier un service"""
    service = get_object_or_404(Service, pk=pk)
    
    if request.method == 'POST':
        form = ServiceForm(request.POST, instance=service)
        if form.is_valid():
            form.save()
            messages.success(request, 'Service modifié avec succès!')
            return redirect('services_list')
    else:
        form = ServiceForm(instance=service)
    
    return render(
        request,
        'gestion/service_form.html',
        {
            'form': form,
            'service': service,
            'couleurs_presets': COULEURS_PRESETS,
            'tags_suggestions': TAGS_SUGGESTIONS,
        }
    )


@manager_required
def service_delete(request, pk):
    """Supprimer un service"""
    service = get_object_or_404(Service, pk=pk)
    if request.method == 'POST':
        service.delete()
        messages.success(request, 'Service supprimé avec succès!')
        return redirect('services_list')
    return render(request, 'gestion/service_confirm_delete.html', {'service': service})




from django.core.cache import cache
@manager_required
def dashboard(request):
    today = timezone.now().date()
    
    # On crée une clé de cache unique pour la journée
    cache_key = f"dashboard_data_{today}"
    
    # On tente de récupérer le contexte depuis le cache
    context = cache.get(cache_key)
    
    # Si le cache est vide (première fois ou invalidation après un paiement)
    if not context:
        # --- CALCUL DU CA DU JOUR ---
        ca_today = RecuClient.objects.filter(date__date=today).aggregate(
            t=Coalesce(Sum('total_global'), Value(0, output_field=DecimalField()))
        )['t']
        
        # --- PÉRIODES ENTRANTES ---
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        month_start = today.replace(day=1)
        
        # --- FONCTION HELPER ---
        def get_period_data(start, end, is_month=False):
            recus = RecuClient.objects.filter(date__date__range=[start, end])
            ca_total = recus.aggregate(t=Coalesce(Sum('total_global'), Value(0, output_field=DecimalField())))['t']
            
            if is_month:
                last_month_end = start - timedelta(days=1)
                last_month_start = last_month_end.replace(day=1)
                ca_precedent = RecuClient.objects.filter(date__date__range=[last_month_start, last_month_end]).aggregate(
                    t=Coalesce(Sum('total_global'), Value(0, output_field=DecimalField()))
                )['t']
            else:
                last_week_start = start - timedelta(days=7)
                last_week_end = end - timedelta(days=7)
                ca_precedent = RecuClient.objects.filter(date__date__range=[last_week_start, last_week_end]).aggregate(
                    t=Coalesce(Sum('total_global'), Value(0, output_field=DecimalField()))
                )['t']
                
            growth = ((ca_total - ca_precedent) / ca_precedent * 100) if ca_precedent > 0 else 100
            
            ca_stats = recus.annotate(day=TruncDay('date')).values('day').annotate(t=Sum('total_global'))
            ca_map = {c['day'].date(): float(c['t'] or 0) for c in ca_stats}
            
            days_count = (end - start).days + 1
            labels, chart_data = [], []
            for i in range(days_count):
                d = start + timedelta(days=i)
                labels.append(d.strftime("%d %b") if days_count > 7 else d.strftime("%a"))
                chart_data.append(ca_map.get(d, 0))

            pay_data = {'ESPECE': 0, 'MOBILE_MONEY': 0, 'CARTE': 0}
            pay_stats = recus.values("mode_paiement").annotate(total=Sum("total_global"))
            for item in pay_stats:
                mode = item['mode_paiement']
                if mode in pay_data:
                    pay_data[mode] = float(item['total'])

            top_emp = list(PaiementEmploye.objects.filter(date_paiement__date__range=[start, end])
                .values('employe__user__last_name')
                .annotate(total=Sum('total_services'))
                .order_by('-total')[:5])
            
            p_pack_qs = PaiementEmploye.objects.filter(
                date_paiement__date__range=[start, end], 
                provenance_pack__isnull=False
            )
            
            stats_packs_volume = (
                p_pack_qs
                .values('pack_instance_id')
                .annotate(qte_vendue=Avg('quantite')) 
                .aggregate(total_volume=Sum('qte_vendue'))
            )
            nb_packs = stats_packs_volume['total_volume'] or 0

            ca_packs_data = p_pack_qs.aggregate(
                t=Coalesce(Sum('total_services'), Value(0, output_field=DecimalField()))
            )
            ca_packs = ca_packs_data['t']
            
            return {
                'ca_total': float(ca_total),
                'ca_growth': round(float(growth), 1),
                'labels': labels,
                'chart_data': chart_data,
                'pay_data': pay_data,
                'top_employes': top_emp,
                'nb_packs': nb_packs,
                'ca_packs': float(ca_packs),
                'part_packs': round((float(ca_packs)/float(ca_total)*100),1) if ca_total > 0 else 0
            }

        data_week = get_period_data(week_start, week_end, is_month=False)
        data_month = get_period_data(month_start, today, is_month=True)
        
        # --- CONTEXTE FINAL ---
        context = {
            'stats': {
                'ca_today': float(ca_today), 
                'chiffre_semaine': data_week['ca_total'],
                'ca_growth': data_week['ca_growth'],
                'nb_packs': data_week['nb_packs'],
                'part_packs': data_week['part_packs'],
                'ca_packs': data_week['ca_packs'],
                'rdv_aujourdhui': PaiementEmploye.objects.filter(date_paiement__date=today).count(),
            },
            'total_espece': data_week['pay_data']['ESPECE'],
            'total_mobile': data_week['pay_data']['MOBILE_MONEY'],
            'total_carte': data_week['pay_data']['CARTE'],
            'employes_stats': data_week['top_employes'],
            'stats_json': json.dumps(
                {'week': data_week, 'month': data_month}, 
                cls=DjangoJSONEncoder
            ),
        }
        
        # On stocke le résultat calculé pour 5 minutes
        cache.set(cache_key, context, timeout=300)
       
    return render(request, 'gestion/dashboard.html', context)



@manager_required
def service_create(request):
    """Créer un nouveau service ou un nouveau pack pour BEL'R"""
    if request.method == 'POST':
        form = ServiceForm(request.POST)

        if form.is_valid():
            service = form.save(commit=False)

            # Données validées du formulaire
            services_inclus = form.cleaned_data.get('services_inclus')
            est_un_pack = form.cleaned_data.get('est_un_pack')

            # Génération d'un code unique si non fourni
            if not service.code:
                service.code = str(uuid.uuid4())[:8].upper()

            # Sécurité logique :
            # si pas pack => aucun service inclus
            if not est_un_pack:
                service.est_un_pack = False

            service.save()

            # Sauvegarde ManyToMany propre
            if est_un_pack and services_inclus:
                service.services_inclus.set(services_inclus)
            else:
                service.services_inclus.clear()

            messages.success(
                request,
                f'Le service "{service.nom}" a été créé avec succès !'
            )
            return redirect('services_list')

        else:
            messages.error(
                request,
                "Erreur de formulaire. Veuillez vérifier les données saisies."
            )
    else:
        form = ServiceForm()

    couleurs_presets = ["#8A2BE2", "#007bff", "#28a745", "#dc3545", "#ffc107", "#e83e8c"]

    return render(request, 'gestion/service_form.html', {
        'form': form,
        'couleurs_presets': couleurs_presets,
    })





from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Prefetch
@employe_required
def services_list(request):
    # 1. Récupération du filtre de catégorie dans l'URL
    active_category_id = request.GET.get('categorie', 'tous')

    # Prefetch des sous-services inclus dans les packs (Évite le N+1)
    sub_services_prefetch = Prefetch(
        "services_inclus",
        queryset=Service.objects.filter(actif=True).only("id", "nom", "prix")
    )

    # 2. Construction du QuerySet de base des Services
    services_queryset = Service.objects.select_related('categorie').prefetch_related(sub_services_prefetch).filter(actif=True)

    # Application du filtre selon l'onglet cliqué
    if active_category_id == 'uncategorized':
        services_queryset = services_queryset.filter(categorie__isnull=True)
    elif active_category_id != 'tous':
        services_queryset = services_queryset.filter(categorie_id=active_category_id)

    services_queryset = services_queryset.order_by('nom')

    # Convertir en liste pour calculer le compteur
    services_list = list(services_queryset)
    has_results = len(services_list) > 0

    # 3. Pagination des cartes de services (ex: 12 services par page pour faire des lignes propres de 3 ou 4 cartes)
    page = request.GET.get('page', 1)
    paginator = Paginator(services_list, 12)

    try:
        services_pagines = paginator.page(page)
    except PageNotAnInteger:
        services_pagines = paginator.page(1)
    except EmptyPage:
        services_pagines = paginator.page(paginator.num_pages)

    # 4. Liste de toutes les catégories pour fabriquer la barre d'onglets
    categories = CategorieService.objects.all()

    return render(request, "gestion/services.html", {
        "services": services_pagines,
        "categories": categories,
        "active_category": active_category_id,
        "has_results": has_results,
    })






@gerant_only
def service_detail(request, service_id):
    """
    VUE BUSINESS INTELLIGENCE BEL'R - VERSION FINALE ULTRA OPTIMISÉE
    Graphiques : Répartition par jour de la semaine + Évolution sur les 12 derniers mois
    """
    # 1. Préchargement pour éviter les requêtes N+1 sur les packs
    item = get_object_or_404(
        Service.objects.prefetch_related('services_inclus'), 
        id=service_id
    )
    
    now = timezone.now()
    today = now.date()
    period = request.GET.get('period', 'month')

    # ==========================================================
    # OUTILS / HELPERS
    # ==========================================================
    def safe_percent(num, den, precision=1):
        try:
            return round((float(num) / float(den)) * 100, precision) if den else 0
        except (TypeError, ValueError, ZeroDivisionError):
            return 0

    def get_period_filter(p):
        q = Q()
        label = "Ce mois"
        if p == 'today':
            q &= Q(date_paiement__date=today)
            label = "Aujourd'hui"
        elif p == 'week':
            start_week = today - timedelta(days=today.weekday())
            end_week = start_week + timedelta(days=6)
            q &= Q(date_paiement__date__range=[start_week, end_week])
            label = "Cette semaine"
        elif p == 'month':
            q &= Q(date_paiement__year=now.year, date_paiement__month=now.month)
            label = "Ce mois"
        elif p == 'year':
            q &= Q(date_paiement__year=now.year)
            label = "Cette année"
        elif p == 'all':
            label = "Toute la période"
        return q, label

    def compute_fidelisation(target_sales_qs):
        clients_stats = (
            target_sales_qs
            .exclude(client_nom__isnull=True)
            .exclude(client_nom="")
            .values('client_nom')
            .annotate(nb=Count('id'))
        )
        clients_list = list(clients_stats)
        total_clients = len(clients_list)

        if total_clients == 0:
            return {
                'taux_repeat_clients': 0, 'moyenne_achats_par_client': 0,
                'clients_1_achat': 0, 'clients_2_3_achats': 0, 'clients_4_plus_achats': 0,
                'repeat_clients': 0, 'badge_fidelisation': "secondary", 'niveau_fidelite': "Faible",
            }

        repeat_clients = sum(1 for x in clients_list if x['nb'] > 1)
        total_achats = sum(x['nb'] for x in clients_list)
        moyenne_achats = round(total_achats / total_clients, 2)
        taux_repeat = safe_percent(repeat_clients, total_clients)

        if moyenne_achats >= 3: badge, niveau = "success", "Excellente"
        elif moyenne_achats >= 2: badge, niveau = "primary", "Bonne"
        elif moyenne_achats >= 1.2: badge, niveau = "info", "Moyenne"
        else: badge, niveau = "secondary", "Faible"

        return {
            'taux_repeat_clients': taux_repeat,
            'moyenne_achats_par_client': moyenne_achats,
            'clients_1_achat': sum(1 for x in clients_list if x['nb'] == 1),
            'clients_2_3_achats': sum(1 for x in clients_list if 2 <= x['nb'] <= 3),
            'clients_4_plus_achats': sum(1 for x in clients_list if x['nb'] >= 4),
            'repeat_clients': repeat_clients,
            'badge_fidelisation': badge,
            'niveau_fidelite': niveau,
        }
    
    def compute_Saisonnalite_et_evolution(base_qs, obj):
        target_filter = Q(provenance_pack=obj) if obj.est_un_pack else Q(services=obj)
        qs = base_qs.filter(target_filter)

        # A. GRAPHE 1 : Jours de la semaine
        jours_stats = qs.annotate(j=ExtractWeekDay('date_paiement')).values('j').annotate(c=Count('id'))
        jours_data = [0] * 7
        for x in jours_stats:
            jours_data[(x['j'] - 1) % 7] = x['c']

        meilleur_jour_index = jours_data.index(max(jours_data)) if any(jours_data) else None
        meilleur_jour_nom = ['Dim', 'Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam'][meilleur_jour_index] if meilleur_jour_index is not None else "-"

        # B. NOUVEAU : Calcul de l'heure d'affluence maximale
        heures_stats = (
            qs.annotate(heure=ExtractHour('date_paiement'))
            .values('heure')
            .annotate(c=Count('id'))
            .order_by('-c')
            .first()
        )
        
        if heures_stats and heures_stats['heure'] is not None:
            # Formate l'affichage (ex: 14h00 - 15h00)
            h_debut = heures_stats['heure']
            meilleure_heure_txt = f"{h_debut}h00"
        else:
            meilleure_heure_txt = "--"

        # C. GRAPHE 2 : Évolution mensuelle sur les 12 derniers mois
        il_y_a_un_an = now - timedelta(days=365)
        qs_historique = PaiementEmploye.objects.filter(target_filter, date_paiement__gte=il_y_a_un_an)
        
        evolution_stats = (
            qs_historique
            .annotate(annee=ExtractYear('date_paiement'), mois=ExtractMonth('date_paiement'))
            .values('annee', 'mois')
            .annotate(c=Count('id'))
            .order_by('annee', 'mois')
        )

        mois_noms = ["Jan", "Fév", "Mar", "Avr", "Mai", "Juu", "Jui", "Aoû", "Sep", "Oct", "Nov", "Déc"]
        evolution_labels = []
        evolution_data = []

        mois_courant = now.month
        annee_courante = now.year
        structure_mois = []
        for i in range(11, -1, -1):
            m = mois_courant - i
            a = annee_courante
            if m <= 0:
                m += 12
                a -= 1
            structure_mois.append((a, m))

        stats_dict = {(x['annee'], x['mois']): x['c'] for x in evolution_stats}
        for a, m in structure_mois:
            evolution_labels.append(f"{mois_noms[m-1]} {str(a)[2:]}")
            evolution_data.append(stats_dict.get((a, m), 0))

        # IMPORTANT : Alignement strict des clés renvoyées avec le HTML
        return {
            'jours_labels': json.dumps(['Dim', 'Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam']),
            'jours_data': json.dumps(jours_data),
            'evolution_labels': json.dumps(evolution_labels),
            'evolution_data': json.dumps(evolution_data),
            'meilleur_jour': meilleur_jour_nom,       # Clé corrigée (sans "s")
            'meilleure_heure': meilleure_heure_txt,   # Nouvelle variable dynamique calculée !
        }
    
    # ==========================================================
    # BASE DATASET & OPTIMISATIONS
    # ==========================================================
    base_filter, label_periode = get_period_filter(period)
    all_sales_global = PaiementEmploye.objects.filter(base_filter)

    stats_globales = list(all_sales_global.values('services').annotate(vol=Count('id'), val=Sum('total_services')))
    max_ventes_salon = max([s['vol'] for s in stats_globales]) if stats_globales else 1
    max_ca_salon_service = max([s['val'] for s in stats_globales]) if stats_globales else Decimal('1')
    
    total_tickets_global = all_sales_global.values('numero_groupe').distinct().count() or 1

    if item.est_un_pack:
        target_sales = all_sales_global.filter(provenance_pack=item)
    else:
        target_sales = all_sales_global.filter(services=item)

    groupes_ids = list(target_sales.order_by().values_list('numero_groupe', flat=True).distinct())
    fidelisation = compute_fidelisation(target_sales)

    context = {
        'object': item,
        'label_periode': label_periode,
        'period': period,
        'fidelisation': fidelisation,
        'tickets_uniques': len(groupes_ids),
        'penetration_globale': safe_percent(len(groupes_ids), total_tickets_global),
    }

    # ==========================================================
    # CAS N°1 : ANALYSE D'UN PACK
    # ==========================================================
    if item.est_un_pack:
        pack = item
        
        ventes_par_ticket = target_sales.values('numero_groupe').annotate(total_ticket_pack=Sum('total_services'))
        pack_prix_float = float(pack.prix) if pack.prix > 0 else 0
        total_packs_vendus = sum([round(float(v['total_ticket_pack']) / pack_prix_float) for v in ventes_par_ticket]) if pack_prix_float > 0 else 0

        prix_theorique = pack.services_inclus.aggregate(total=Coalesce(Sum('prix'), Decimal('0')))['total']

        stats_globale_pack = target_sales.aggregate(
            total_utilisations=Count('id'),
            ca_ventile=Coalesce(Sum('total_services'), Decimal('0')),
            tickets_distincts=Count('numero_groupe', distinct=True),
        )
        tickets_distincts = stats_globale_pack['tickets_distincts'] or 0
        services_stats_pack = []
        nb_locomotives = 0

        services_inclus = list(pack.services_inclus.all())
        services_ids = [s.id for s in services_inclus]

        # Recettes chargées en bloc
        recettes_globales = ConsommableService.objects.filter(service_id__in=services_ids).select_related('produit')
        cout_par_service = {}
        for r in recettes_globales:
            cout_par_service[r.service_id] = cout_par_service.get(r.service_id, Decimal('0')) + (r.quantite_prevue * r.produit.prix_achat_moyen)

        # Correction ici : Utilisation du champ 'services' (et non 'services_id')
        stats_services_global = all_sales_global.filter(services__in=services_ids).values('services').annotate(
            total=Count('id', distinct=True),
            solo=Count('id', filter=Q(provenance_pack__isnull=True), distinct=True)
        )
        stats_services_map = {x['services']: x for x in stats_services_global}

        utilisations_map = dict(
            target_sales.filter(services__in=services_ids)
            .values('services')
            .annotate(c=Count('numero_groupe', distinct=True))
            .values_list('services', 'c')
        )

        cout_total_produits_pack = Decimal('0')
       

        for s in services_inclus:
            # 1. Calculs financiers des coûts de consommables
            cout_service = cout_par_service.get(s.id, Decimal('0'))
            cout_total_produits_pack += cout_service
            utilisation_dans_pack = utilisations_map.get(s.id, 0)

            # 2. Statistiques de vente pour déterminer le rôle (Locomotive vs Wagon)
            s_stats = stats_services_map.get(s.id, {'solo': 0, 'total': 0})
            ventes_solo = s_stats['solo'] or 0
            total_vente_service = s_stats['total'] or 0
            
            penetration_solo = safe_percent(ventes_solo, total_vente_service)
            is_locomotive = penetration_solo >= 40
            if is_locomotive:
                nb_locomotives += 1

            # 3. Calcul de la santé de la marge pour ce service précis
            # Seuil critique : si le coût des produits dépasse 30% du prix du service, la marge est en danger
            prix_service = s.prix if hasattr(s, 'prix') and s.prix else Decimal('1')
            prorata_ligne = (cout_service / prix_service) * 100
            conflit_marge_ligne = prorata_ligne > 30  # True si la marge est critique

            # 4. Injection finale avec TOUTES les données requises par le template
            services_stats_pack.append({
                'service': {
                    'nom': s.nom,
                },
                'prix_theorique': s.prix if hasattr(s, 'prix') else Decimal('0'),
                'is_locomotive': is_locomotive,
                'conflit_marge_ligne': conflit_marge_ligne,  # Revoilà la donnée manquante !
                'taux_realisation': safe_percent(utilisation_dans_pack, tickets_distincts),
                'pene_solo': penetration_solo,
                'type': "Locomotive" if is_locomotive else "Wagon",
                'badge': "success" if is_locomotive else "info",
            })

        if pack.prix > 0:
            prorata_theorique = (cout_total_produits_pack / pack.prix) * 100
            marge_unitaire_theorique = pack.prix - cout_total_produits_pack
        else:
            prorata_theorique = marge_unitaire_theorique = Decimal('0')

        remise_faciale = safe_percent(prix_theorique - pack.prix, prix_theorique)
        taux_utilisation_par_ticket = safe_percent(stats_globale_pack['total_utilisations'], tickets_distincts)

        score_coherence = 100
        if nb_locomotives > 1: score_coherence -= 20
        if remise_faciale > 35: score_coherence -= 15
        if prorata_theorique > 25: score_coherence -= 20
        if fidelisation.get('taux_repeat_clients', 0) < 20: score_coherence -= 10
        score_coherence = max(0, score_coherence)

        context.update({
            'is_pack': True, 'prorata_theorique': prorata_theorique,
            'marge_unitaire_theorique': marge_unitaire_theorique, 'cout_total_produits': cout_total_produits_pack,
            'penetration_service': context.get('penetration_globale', 0), 'prix_pack': pack.prix,
            'prix_theorique': prix_theorique, 'remise_faciale': remise_faciale, 'total_utilisations': total_packs_vendus,
            'ca_ventile': stats_globale_pack['ca_ventile'], 'tickets_uniques': tickets_distincts,
            'lignes_pack': services_stats_pack, 'conflit_marge': nb_locomotives > 1,
            'nb_locomotives': nb_locomotives, 'taux_utilisation_par_ticket': taux_utilisation_par_ticket,
            'score_coherence_pack': score_coherence,
        })

    # ==========================================================
    # CAS N°2 : ANALYSE D'UN SERVICE SOLO
    # ==========================================================
    else:
        service = item
        stats = target_sales.aggregate(
            total_ventes=Count('id'),
            ca_service=Coalesce(Sum('total_services'), Decimal('0')),
            ventes_via_pack=Count('id', filter=Q(provenance_pack__isnull=False)),
        )
        total_ventes = stats['total_ventes'] or 0

        recettes = ConsommableService.objects.filter(service=service).select_related('produit')
        cout_total_produits = Decimal('0')
        for r in recettes:
            r.cout_unitaire = r.quantite_prevue * r.produit.prix_achat_moyen
            cout_total_produits += r.cout_unitaire

        prix_vente_service = getattr(service, 'prix', Decimal('0'))
        if prix_vente_service > 0:
            prorata_theorique = (cout_total_produits / prix_vente_service) * 100
            marge_unitaire_theorique = prix_vente_service - cout_total_produits
        else:
            prorata_theorique = marge_unitaire_theorique = Decimal('0')

        partenaires_B = list(
            all_sales_global
            .filter(numero_groupe__in=groupes_ids)
            .exclude(services=service)
            .exclude(services__isnull=True)
            .values('services', 'services__nom')
            .annotate(freq=Count('numero_groupe', distinct=True))
            .order_by('-freq')[:3]
        )

        recommandations_triples = []
        if partenaires_B:
            partenaires_ids = [b['services'] for b in partenaires_B]
            
            # Correction ici : Utilisation du champ 'services' (et non 'services_id')
            tickets_partenaires = all_sales_global.filter(services__in=partenaires_ids).values('services', 'numero_groupe')
            tickets_map = {}
            for t in tickets_partenaires:
                tickets_map.setdefault(t['services'], []).append(t['numero_groupe'])

            for b in partenaires_B:
                list_tickets_b = tickets_map.get(b['services'], [])
                c_candidate = (
                    all_sales_global
                    .filter(numero_groupe__in=list_tickets_b)
                    .exclude(services=b['services'])
                    .exclude(services=service)
                    .exclude(services__isnull=True)
                    .values('services', 'services__nom')
                    .annotate(freq=Count('numero_groupe', distinct=True))
                    .order_by('-freq')
                    .first()
                )

                if c_candidate:
                    recommandations_triples.append({
                        'service_b': b['services__nom'],
                        'service_c': c_candidate['services__nom'],
                        'force': b['freq'],
                        'est_optimal': True,
                        'raison': "Duo de choc détecté",
                    })

        ca_global_recus = RecuClient.objects.filter(numero_groupe__in=groupes_ids).aggregate(
            s=Coalesce(Sum('total_global'), Decimal('0'))
        )['s'] or Decimal('1')

        part_ticket = safe_percent(stats['ca_service'], ca_global_recus)
        taux_conversion_pack = safe_percent(stats['ventes_via_pack'], total_ventes)
        
        nb_tickets_service = target_sales.order_by().values('numero_groupe').distinct().count()
        penetration_service = safe_percent(nb_tickets_service, total_tickets_global)

        # Optimisation exclusivité
        tickets_uniques_comptage = (
            all_sales_global
            .filter(numero_groupe__in=groupes_ids)
            .values('numero_groupe')
            .annotate(total_occurrences=Count('id'))
        )
        ventes_seules = sum(1 for t in tickets_uniques_comptage if t['total_occurrences'] == 1)
        taux_exclusivite = safe_percent(ventes_seules, total_ventes)

        p_vol = (total_ventes / max_ventes_salon) * 25
        p_rent = (float(stats['ca_service']) / float(max_ca_salon_service)) * 25
        p_marge_pure = 15 if prorata_theorique < 15 else (10 if prorata_theorique < 30 else 0)
        p_pene = (context['penetration_globale'] / 100) * 25
        p_exclu = (taux_exclusivite / 100) * 10
        
        score = min(100, int(p_vol + p_rent + p_pene + p_exclu + p_marge_pure))

        if score >= 80: classe_strategique, badge_strategique = ("STAR", "Moteur d'excellence."), "success"
        elif score >= 55: classe_strategique, badge_strategique = ("PILIER", "Service solide."), "primary"
        elif score >= 30: classe_strategique, badge_strategique = ("POTENTIEL", "À booster."), "warning"
        else: classe_strategique, badge_strategique = ("FAIBLE TRACTION", "Peu rentable."), "secondary"

        context.update({
            'is_pack': False, 'total_ventes': total_ventes,
            'prorata_theorique': prorata_theorique, 'marge_unitaire_theorique': marge_unitaire_theorique,
            'cout_total_produits': cout_total_produits, 'ca_service': stats['ca_service'],
            'ventes_via_pack': stats['ventes_via_pack'], 'taux_conversion_pack': taux_conversion_pack,
            'recommandations_triples': recommandations_triples, 'score_strategique': score,
            'classe_strategique': classe_strategique, 'badge_strategique': badge_strategique,
            'part_ticket': part_ticket, 'penetration_service': penetration_service,
        })

    # ==========================================================
    # SAISONNALITÉ & INSIGHTS TEMPORELS (MISE À JOUR DES GRAPHES)
    # ==========================================================
    saisonnalite = compute_Saisonnalite_et_evolution(all_sales_global, item)
    context.update(saisonnalite)

    return render(request, 'gestion/detail.html', context)

