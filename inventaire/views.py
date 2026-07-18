# ==========================================
# 1. Standard Library Imports
# ==========================================
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
import time

# ==========================================
# 2. Django Core & Third-Party Imports
# ==========================================
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import transaction
from django.db.models import (
    Case, Count, DecimalField, ExpressionWrapper, F,
    When, Q, Sum, OuterRef, Subquery, Value
)
from django.db.models.functions import Coalesce
from django.shortcuts import (
    get_object_or_404, redirect, render
)
from django.utils import timezone

# ==========================================
# 3. Local App Imports (Modèles, Formulaires, Décorateurs)
# ==========================================
from authentification.decorator import employe_required, gerant_only, manager_required

from .forms import (
    ChargeExploitationForm,
    ConsommableFormSet,
    PaiementChargeForm,
    ProduitForm,
    MSG_ERREUR_FR,
)
from .models import (
    CategorieProduit,
    ChargeExploitation,
    ConsommableService,
    DosageHistorique,
    MouvementStock,
    PaiementCharge,
    Produit,
    StockMensuelSnapshot,
)

# Imports externes spécifiques (si utilisés dans le projet)
from dateutil.relativedelta import relativedelta
from django.db import connection
from django.db.models import ExpressionWrapper, DecimalField  # déjà dans le bloc django.db.models, supprimer si redondant
from rendezvous.models import PaiementEmploye




@login_required
def creer_produit(request, pk=None):
    produit = get_object_or_404(Produit, pk=pk) if pk else None
    est_edition = produit is not None

    # 🆕 RÉCUPÉRATION DU DERNIER CODE DE RÉFÉRENCE ENREGISTRÉ
    dernier_produit = Produit.objects.exclude(code="").order_by('-id').first()
    dernier_code = dernier_produit.code if dernier_produit else "Aucun"

    if request.method == 'POST' and 'action_supprimer' in request.POST:
        if est_edition:
            nom_produit = produit.nom
            produit.delete() 
            messages.success(request, f"Le produit '{nom_produit}' a été définitivement supprimé.")
        return redirect('inventaire:liste_produits')

    if request.method == 'POST':
        form = ProduitForm(request.POST, instance=produit)
        formset = ConsommableFormSet(request.POST, instance=produit)
        
        est_carburant = request.POST.get('est_carburant') == 'on'
        form_valide = form.is_valid()
        formset_valide = formset.is_valid()

        if not est_carburant:
            lignes_actives = 0
            for i, f in enumerate(formset.forms):
                # Si la ligne est soumise vide mais requise, on force une erreur visible sur le champ
                if not f.cleaned_data.get('service') and not f.fields['service'].widget.attrs.get('disabled'):
                    f.add_error('service', MSG_ERREUR_FR['required'])
                    formset_valide = False
                if f.cleaned_data.get('rendement_par_unite') is None and not f.fields['rendement_par_unite'].widget.attrs.get('disabled'):
                    f.add_error('rendement_par_unite', MSG_ERREUR_FR['required'])
                    formset_valide = False
                
                if f.cleaned_data and not f.cleaned_data.get('DELETE', False):
                    lignes_actives += 1
            
            if lignes_actives == 0:
                formset_valide = False
                messages.error(request, "Estimation Rendement — Au moins un service associé est obligatoire.")

        if form_valide and formset_valide:
            try:
                with transaction.atomic():
                    produit = form.save()
                    formset.instance = produit
                    formset.save()
                return redirect('inventaire:liste_produits')
            except Exception as e:
                messages.error(request, f"Une erreur technique : {e}")
        else:
            # Votre bloc existant de traitement/interception des erreurs...
            pass
    else:
        form = ProduitForm(instance=produit)
        formset = ConsommableFormSet(instance=produit)
        
        # Ajouter le placeholder dynamique lors d'une création à vide
        if not est_edition:
            form.fields['code'].widget.attrs['placeholder'] = f"Ex dernier code : {dernier_code}"
    
    return render(request, 'inventaire/creer_produit.html', {
        'form': form,
        'formset': formset,
        'est_edition': est_edition,
        'produit': produit,
        'dernier_code': dernier_code # Envoi au template
    })





@manager_required
def modifier_mouvement(request, pk):
    mouvement = get_object_or_404(MouvementStock, pk=pk)
    produit = mouvement.produit
    if request.method == 'POST':
        # On peut ici modifier la quantité, le type ou la note
        mouvement.quantite = Decimal(request.POST.get('quantite'))
        mouvement.type_mouvement = request.POST.get('type_mouvement')
        mouvement.notes = request.POST.get('notes')
        mouvement.save() # Le signal/save du modèle recalculera le stock produit
        messages.success(request, "Mouvement mis à jour.")
        return redirect('inventaire:detail_produit', produit_id=produit.pk)
    
    return render(request, 'inventaire/modifier_mouvement.html', {'mouvement': mouvement})




@manager_required
def supprimer_mouvement(request, pk):
    mouvement = get_object_or_404(MouvementStock, pk=pk)
    produit = mouvement.produit
    if request.method == 'POST':
        mouvement.delete() # Le signal/save du modèle doit gérer la remise à niveau du stock
        messages.success(request, "Mouvement supprimé.")
        return redirect('inventaire:detail_produit', produit_id=produit.pk)
    return render(request, 'inventaire/confirmer_suppression.html', {'mouvement': mouvement})





@manager_required
def ajouter_mouvement_pamp(request, produit_id=None, mouvement_id=None):
    # --- SÉCURITÉ & DROITS D'ACCÈS DU MANAGER ---
    is_manager = request.user.is_superuser or request.user.groups.filter(name='Manager').exists()
    
    if not is_manager:
        messages.error(request, "Accès refusé : Seul le Manager est autorisé à manipuler le stock.")
        return redirect('inventaire:liste_produits')

    mouvement = None
    produit = None
    is_edit = False

    if mouvement_id:
        mouvement = get_object_or_404(MouvementStock, pk=mouvement_id)
        produit = mouvement.produit
        is_edit = True
    else:
        produit = get_object_or_404(Produit, pk=produit_id)
        mouvement = MouvementStock(produit=produit)

    if request.method == 'POST':
        # --- SUPPRESSION AVEC GARDE-FOU CHRONOLOGIQUE ---
        if 'delete_mouvement' in request.POST and is_edit:
            try:
                mouvement.delete()
                messages.warning(request, "Mouvement de stock supprimé avec succès.")
                return redirect('inventaire:liste_produits')
            except ValidationError as e:
                # Interception du blocage chronologique (ex: inventaire plus récent existant)
                messages.error(request, f"Erreur de suppression : {e.message if hasattr(e, 'message') else e}")
                return render(request, 'inventaire/form_mouvement.html', {
                    'produit': produit, 
                    'mouvement': mouvement, 
                    'is_edit': is_edit
                })

        # --- LECTURE DES DONNÉES DU FORMULAIRE ---
        type_mouv = request.POST.get('type_mouvement')
        raw_qte = request.POST.get('quantite', '').strip()
        raw_prix_u = request.POST.get('prix_achat_unitaire', '').strip()

        # Validation stricte : Aucun choix par défaut autorisé à la validation
        if not type_mouv:
            messages.error(request, "Veuillez sélectionner un type de mouvement.")
            return render(request, 'inventaire/form_mouvement.html', {'produit': produit, 'mouvement': mouvement, 'is_edit': is_edit})

        if not raw_qte:
            messages.error(request, "La quantité (ou le reste physique) ne peut pas être vide.")
            return render(request, 'inventaire/form_mouvement.html', {'produit': produit, 'mouvement': mouvement, 'is_edit': is_edit})

        try:
            qte = Decimal(raw_qte.replace(',', '.'))
            prix_u = Decimal(raw_prix_u.replace(',', '.')) if raw_prix_u else Decimal('0')
        except (InvalidOperation, TypeError):
            messages.error(request, "Erreur de format dans les montants ou les quantités saisis.")
            return render(request, 'inventaire/form_mouvement.html', {
                'produit': produit, 
                'mouvement': mouvement, 
                'is_edit': is_edit
            })

       # --- ENREGISTREMENT AVEC GARDE-FOU VALIDATION ---
        mouvement.type_mouvement = type_mouv
        mouvement.quantite = qte
        mouvement.prix_achat_unitaire = prix_u if type_mouv == 'ENTREE' else None
        mouvement.notes = request.POST.get('notes')
        
        if not is_edit:
            mouvement.created_by = request.user
        
        try:
            mouvement.save()
            produit.refresh_from_db()
            messages.success(request, f"Données de stock enregistrées avec succès par le Manager ({request.user.username}).")
            return redirect('inventaire:liste_produits')
            
        except ValidationError as e:
            # 📝 EXTRACTION PROPRE ET SÉCURISÉE DES MESSAGES DE VALIDATION DJANGO
            if hasattr(e, 'message_dict'):
                # Si l'erreur est liée à un champ spécifique (ex: {'quantite': ['Message...']})
                error_msg = ", ".join([f"{', '.join(v)}" for k, v in e.message_dict.items()])
            elif hasattr(e, 'messages'):
                # Si c'est une liste globale de messages
                error_msg = ", ".join(e.messages)
            else:
                error_msg = str(e)

            messages.error(request, f"Erreur de cohérence : {error_msg}")
            return render(request, 'inventaire/form_mouvement.html', {
                'produit': produit, 
                'mouvement': mouvement, 
                'is_edit': is_edit
            })

    return render(request, 'inventaire/form_mouvement.html', {
        'produit': produit,
        'mouvement': mouvement,
        'is_edit': is_edit
    })









@manager_required
def creer_charge(request, pk=None):
    # Si pk est présent, c'est une modification, sinon c'est une création
    charge = get_object_or_404(ChargeExploitation, pk=pk) if pk else None
    
    if request.method == 'POST':
        # instance=charge permet à Django de savoir s'il doit UPDATE ou INSERT
        form = ChargeExploitationForm(request.POST, instance=charge)
        if form.is_valid():
            form.save()
            messages.success(request, "La charge a été enregistrée avec succès.")
            return redirect('inventaire:liste_charges')
    else:
        form = ChargeExploitationForm(instance=charge)
    
    context = {
        'form': form,
        'edit_mode': pk is not None,
        'charge': charge
    }
    return render(request, 'inventaire/creer_charge.html', context)


@manager_required
def enregistrer_paiement(request, charge_id, paiement_id=None):
    # 1. Récupération de la charge
    charge = get_object_or_404(ChargeExploitation, id=charge_id)
    
    # 2. Récupération du paiement si on est en mode modification
    paiement = None
    if paiement_id:
        paiement = get_object_or_404(PaiementCharge, id=paiement_id, charge=charge)

    if request.method == 'POST':
        form = PaiementChargeForm(request.POST, request.FILES, instance=paiement)
        
        if form.is_valid():
            # Utilisation d'un bloc transaction pour s'assurer que si l'un échoue, rien n'est sauvé
            with transaction.atomic():
                # Sauvegarde du paiement
                paiement = form.save(commit=False)
                paiement.charge = charge
                paiement.save()

                # --- LOGIQUE DE RECALCUL DU STATUT DE LA CHARGE ---
                # On récupère la somme de TOUS les paiements liés à cette charge
                # (Y compris celui qu'on vient de modifier/créer)
                total_verse = sum(p.montant_verse for p in charge.paiements.all())
                
                # Mise à jour du statut 'est_payee'
                # On utilise une petite marge d'erreur pour les calculs de décimaux si nécessaire
                if total_verse >= charge.montant_total:
                    charge.est_payee = True
                else:
                    charge.est_payee = False
                
                charge.save()
                # --------------------------------------------------

            return redirect('inventaire:liste_charges')
    else:
        # Mode GET : Initialisation du formulaire
        if paiement:
            # En modification, le formulaire prend les données de l'instance 'paiement'
            form = PaiementChargeForm(instance=paiement)
        else:
            # En création, on pré-remplit avec le reste à payer actuel
            form = PaiementChargeForm(initial={'montant_verse': charge.reste_a_payer})
    
    context = {
        'form': form,
        'charge': charge,
        'modification': paiement_id is not None,
    }
    
    return render(request, 'inventaire/payer_charge.html', context)


@manager_required
def modifier_charge(request, pk):
    charge = get_object_or_404(ChargeExploitation, pk=pk)
    form = ChargeExploitationForm(request.POST or None, instance=charge)
    if form.is_valid():
        form.save()
        messages.success(request, "La charge a été modifiée avec succès.")
        return redirect('inventaire:liste_charges')
    return render(request, 'inventaire/creer_charge.html', {'form': form, 'edit_mode': True})


@manager_required
def supprimer_charge(request, pk):
    charge = get_object_or_404(ChargeExploitation, pk=pk)
    if request.method == 'POST':
        charge.delete()
        messages.warning(request, "La charge a été supprimée.")
        return redirect('inventaire:liste_charges')
    return render(request, 'inventaire/confirmer_suppression.html', {'objet': charge})

# --- GESTION DES PAIEMENTS ---





@manager_required
def modifier_paiement(request, pk):
    paiement = get_object_or_404(PaiementCharge, pk=pk)
    charge = paiement.charge
    
    # On charge le formulaire avec l'instance existante
    form = PaiementChargeForm(request.POST or None, request.FILES or None, instance=paiement)
    
    if request.method == 'POST':
        if form.is_valid():
            with transaction.atomic():
                # 1. On sauvegarde le paiement modifié
                paiement = form.save()
                
                # 2. On force Django à recharger la charge pour voir le nouveau montant_paye
                charge.refresh_from_db()
                
                # 3. Logique BEL'R : On ajuste le total de la charge au montant payé
                # Si tu changes 7000 en 1000, le montant_total de la facture devient 1000
                charge.montant_total = charge.montant_paye
                
                # 4. On s'assure que le statut est correct
                charge.est_payee = (charge.montant_paye >= charge.montant_total)
                charge.save()
            
            messages.success(request, "Paiement mis à jour avec succès.")
            return redirect('inventaire:liste_charges')
            
    return render(request, 'inventaire/payer_charge.html', {
        'form': form, 
        'charge': charge, 
        'edit_mode': True
    })












@manager_required
def supprimer_paiement(request, pk):
    paiement = get_object_or_404(PaiementCharge, pk=pk)
    charge = paiement.charge
    
    if request.method == 'POST':
        # Avant de supprimer, on peut choisir de remettre le montant_total à 0 
        # si c'était une charge variable, pour forcer une nouvelle saisie
        paiement.delete()
        
        # Mise à jour du statut de la charge
        charge.est_payee = False
        charge.save()
        
        messages.warning(request, "Le paiement a été annulé et la charge est de nouveau 'En attente'.")
        return redirect('inventaire:liste_charges')

    return render(request, 'inventaire/confirmer_suppression.html', {
        'objet': f"le paiement de {paiement.montant_verse} FCFA pour {charge.libelle}"
    })






@manager_required
def historique_mouvements(request):
    maintenant = timezone.now()
    mois_select = request.GET.get('mois', str(maintenant.month))
    annee_select = request.GET.get('annee', str(maintenant.year))
    
    # --- FILTRAGE ET PAGINATION DES PAIEMENTS ---
    paiements_query = PaiementCharge.objects.select_related('charge')
    
    if mois_select != "all":
        paiements_query = paiements_query.filter(
            date_paiement__month=mois_select, 
            date_paiement__year=annee_select
        )

    paiements_recents_all = paiements_query.order_by('-date_paiement')
    
    # État vide pour les paiements
    has_paiements = paiements_recents_all.exists()
    
    # Pagination : 15 paiements par page
    paginator_paiements = Paginator(paiements_recents_all, 15)
    page_paiements = request.GET.get('page_paiements')
    try:
        paiements_recents = paginator_paiements.page(page_paiements)
    except PageNotAnInteger:
        paiements_recents = paginator_paiements.page(1)
    except EmptyPage:
        paiements_recents = paginator_paiements.page(paginator_paiements.num_pages)

    # --- CHARGES EN ATTENTE ---
    charges_en_attente = ChargeExploitation.objects.filter(est_payee=False).order_by('date_echeance')
    
    # État vide pour les charges
    has_charges_en_attente = charges_en_attente.exists()
    
    # Calcul du total dû
    total_du = sum(c.reste_a_payer for c in charges_en_attente)
    
    liste_mois = [
        {'id': 1, 'nom': 'Janvier'}, {'id': 2, 'nom': 'Février'}, {'id': 3, 'nom': 'Mars'},
        {'id': 4, 'nom': 'Avril'}, {'id': 5, 'nom': 'Mai'}, {'id': 6, 'nom': 'Juin'},
        {'id': 7, 'nom': 'Juillet'}, {'id': 8, 'nom': 'Août'}, {'id': 9, 'nom': 'Septembre'},
        {'id': 10, 'nom': 'Octobre'}, {'id': 11, 'nom': 'Novembre'}, {'id': 12, 'nom': 'Décembre'}
    ]

    context = {
        'charges_en_attente': charges_en_attente,
        'has_charges_en_attente': has_charges_en_attente,
        'paiements_recents': paiements_recents,
        'has_paiements': has_paiements,
        'total_du': total_du,
        'liste_mois': liste_mois,
        'mois_select': mois_select,
        'annee_select': annee_select,
    }
    return render(request, 'inventaire/historique_mouvement.html', context)




@manager_required
def historique_mouvements_global(request):
    maintenant = timezone.now()
    
    # 1. Récupération des paramètres
    recherche = request.GET.get('q', '').strip()
    type_filtre = request.GET.get('type_mouvement', '').strip()
    mois_filtre = request.GET.get('mois', str(maintenant.month)).strip()
    annee_filtre = request.GET.get('annee', str(maintenant.year)).strip()

    # Requête de base (uniquement les actions manuelles)
    mouvements_query = MouvementStock.objects.select_related('produit', 'created_by').filter(is_automatique=False)

    # 2. Application dynamique des filtres
    if recherche:
        mouvements_query = mouvements_query.filter(
            Q(produit__nom__icontains=recherche) | 
            Q(produit__code__icontains=recherche) | 
            Q(notes__icontains=recherche)
        )
        
    if type_filtre and type_filtre in ['ENTREE', 'SORTIE']:
        mouvements_query = mouvements_query.filter(type_mouvement=type_filtre)
        
    if mois_filtre and mois_filtre.isdigit():
        mouvements_query = mouvements_query.filter(date_mouvement__month=int(mois_filtre))
        
    if annee_filtre and annee_filtre.isdigit():
        mouvements_query = mouvements_query.filter(date_mouvement__year=int(annee_filtre))

    # Tri final décroissant
    mouvements_query = mouvements_query.order_by('-date_mouvement')

    # ÉTAT VIDE : On vérifie si la requête filtrée contient des éléments
    has_results = mouvements_query.exists()

    # 3. Formatage pour l'affichage (réalisé efficacement sur le QuerySet)
    for mv in mouvements_query:
        pamp = mv.produit.prix_achat_moyen or Decimal('0')
        
        if mv.type_mouvement == 'ENTREE':
            mv.quantite_a_afficher = mv.quantite
            mv.prix_total_achat = mv.quantite * (mv.prix_achat_unitaire or pamp)
            mv.badge_style = "bg-light-success text-success"
            mv.type_label = "Achat / Entrée"
        elif mv.type_mouvement == 'SORTIE':
            mv.quantite_a_afficher = mv.quantite
            mv.prix_total_achat = None
            mv.badge_style = "bg-light-warning text-warning"
            mv.type_label = "Reste Déclaré"

    # 4. CONFIGURATION DE LA PAGINATION (15 mouvements par page)
    paginator = Paginator(mouvements_query, 15)
    page = request.GET.get('page')
    
    try:
        mouvements_pagines = paginator.page(page)
    except PageNotAnInteger:
        mouvements_pagines = paginator.page(1)
    except EmptyPage:
        mouvements_pagines = paginator.page(paginator.num_pages)

    # Listes pour alimenter les balises <select>
    mois_liste = [
        ('1', 'Janvier'), ('2', 'Février'), ('3', 'Mars'), ('4', 'Avril'), 
        ('5', 'Mai'), ('6', 'Juin'), ('7', 'Juillet'), ('8', 'Août'), 
        ('9', 'Septembre'), ('10', 'Octobre'), ('11', 'Novembre'), ('12', 'Décembre')
    ]
    annees_liste = [str(maintenant.year - i) for i in range(3)]

    context = {
        'mouvements': mouvements_pagines,  # Contient l'objet Page paginé
        'has_results': has_results,        # Indicateur booléen d'état vide
        'mois_liste': mois_liste,
        'annees_liste': annees_liste,
        'mois_actuel': mois_filtre,
        'annee_actuelle': annee_filtre,
        'type_actuel': type_filtre,
        'q': recherche,
    }
    return render(request, 'inventaire/historique_global.html', context)











from django.shortcuts import render
from django.db.models import Q, F, Sum, Count, Case, When, ExpressionWrapper, DecimalField, Subquery, OuterRef
from django.db.models.functions import Coalesce
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage
from django.utils import timezone
from datetime import datetime
from dateutil.relativedelta import relativedelta
from collections import defaultdict
from decimal import Decimal
import time

from django.db.models import Value


@manager_required
def liste_produits(request):
    """
    Vue BI optimisée au maximum pour la vitesse.
    Calculs des KPIs globaux déportés en BDD pour éviter les données erronées liées à la pagination.
    """
    maintenant = timezone.now()

    # 1. Filtres et Recherche
    recherche = request.GET.get('q', '')
    categorie_id = request.GET.get('categorie')
    mois_filtre = int(request.GET.get('mois', maintenant.month))
    annee_filtre = int(request.GET.get('annee', maintenant.year))

    # ⚡ Récupération du critère de tri depuis l'URL (Défaut: 'nom')
    # Valeurs gérées par le manager : 'nom', 'alerte', 'consommation', 'recent'
    tri_choisi = request.GET.get('tri', 'nom')

    est_mois_en_cours = (mois_filtre == maintenant.month and annee_filtre == maintenant.year)

    # Base du QuerySet commun incluant le tri dynamique en base de données
    produits_queryset = Produit.objects.select_related('categorie').filter(actif=True).classer_selon_critere(
        critere=tri_choisi,
        mois=mois_filtre,
        annee=annee_filtre
    )

    if recherche:
        produits_queryset = produits_queryset.filter(Q(nom__icontains=recherche) | Q(code__icontains=recherche))
    if categorie_id:
        produits_queryset = produits_queryset.filter(categorie_id=categorie_id)

    # 2. Séparation de la logique d'annotation selon la temporalité
    # 2. Séparation de la logique d'annotation selon la temporalité
    if est_mois_en_cours:
        snap_subquery = StockMensuelSnapshot.objects.filter(
            produit_id=OuterRef('pk'), mois=mois_filtre, annee=annee_filtre
        )

        produits_anotes = produits_queryset.annotate(
            pamp_calculé=Coalesce(F('prix_achat_moyen'), Decimal('0')),
            
            # 🔥 SÉCURITÉ ABSOLUE : Si le produit a été créé durant le mois en cours, 
            # son stock initial au 1er du mois est forcément 0, snapshot ou pas !
            debut_mois_reel=Case(
                When(
                    created_at__month=mois_filtre,
                    created_at__year=annee_filtre,
                    then=Value(Decimal('0'))
                ),
                default=Coalesce(
                    Subquery(snap_subquery.values('quantite_initiale_reelle')[:1]),
                    Decimal('0')
                ),
                output_field=DecimalField(max_digits=10, decimal_places=2)
            ),
            stock_dispo_reel=F('quantite_stock')
        )
    else:
        snap_subquery = StockMensuelSnapshot.objects.filter(
            produit_id=OuterRef('pk'), mois=mois_filtre, annee=annee_filtre
        )

        # Si le produit a été créé APRÈS le mois passé qu'on consulte, il n'existait pas encore => 0 partout
        produits_anotes = produits_queryset.annotate(
            pamp_calculé=Coalesce(Subquery(snap_subquery.values('pamp_historique')[:1]), Decimal('0')),
            debut_mois_reel=Case(
                When(
                    created_at__gt=timezone.datetime(annee_filtre, mois_filtre, 1, tzinfo=timezone.get_current_timezone()),
                    then=Value(Decimal('0'))
                ),
                default=Coalesce(Subquery(snap_subquery.values('quantite_initiale_reelle')[:1]), Decimal('0')),
                output_field=DecimalField(max_digits=10, decimal_places=2)
            ),
            stock_dispo_reel=Coalesce(Subquery(snap_subquery.values('quantite_finale_reelle')[:1]), Decimal('0'))
        )

    # 3. Application des calculs financiers (Commun aux deux branches)
    produits_anotes = produits_anotes.annotate(
        valeur_debut_mois_reel=ExpressionWrapper(
            F('debut_mois_reel') * F('pamp_calculé'),
            output_field=DecimalField(max_digits=12, decimal_places=2)
        ),
        valeur_actuelle_reelle=ExpressionWrapper(
            F('stock_dispo_reel') * F('pamp_calculé'),
            output_field=DecimalField(max_digits=12, decimal_places=2)
        )
    )

    # ⚡ 4. CALCUL DES TOTALIZATIONS GLOBALES EN BDD (Avant pagination)
    totaux_globaux = produits_anotes.aggregate(
        total_initial=Sum('valeur_debut_mois_reel'),
        total_actuel=Sum('valeur_actuelle_reelle')
    )
    valeur_initiale_totale_reelle = totaux_globaux['total_initial'] or Decimal('0')
    valeur_totale = totaux_globaux['total_actuel'] or Decimal('0')

    # 5. Pagination
    page = request.GET.get('page', 1)
    paginator = Paginator(produits_anotes, 20)

    try:
        produits_pagines = paginator.page(page)
    except PageNotAnInteger:
        produits_pagines = paginator.page(1)
    except EmptyPage:
        produits_pagines = paginator.page(paginator.num_pages)

    # === LIGNES DE DEBUG À AJOUTER TEMPORAIREMENT ===
    for prod in produits_pagines.object_list:
        if prod.nom == "NOM_DE_TON_PRODUIT_NEUF": # Remplace par le nom du produit qui pose problème
            print(f"--- DEBUG {prod.nom} ---")
            print(f"Début de mois réel (Python): {prod.debut_mois_reel}")
            print(f"Entrées du mois: {prod.total_entrees}")
            print(f"Stock en BDD (quantite_stock): {prod.quantite_stock}")
    # ===============================================

    

    # 6. Rendu du contexte
    return render(request, 'inventaire/alert_stock.html', {
        'produits': produits_pagines,
        'has_results': produits_anotes.exists(),
        'categories': CategorieProduit.objects.all(),
        'valeur_totale': valeur_totale,
        'valeur_initiale_totale_reelle': valeur_initiale_totale_reelle,
        'mois_actuel': mois_filtre,
        'annee_actuelle': annee_filtre,
        'q': recherche,
        'categorie_selectionnee': categorie_id,
        'tri_actuel': tri_choisi,  # Ajouté pour conserver l'état graphique du bouton actif dans le template
    })



def liste_produits_bi(request):
    """
    Vue BI globale BEL'R.
    Calculs des KPIs globaux exécutés entièrement côté BDD pour préserver les performances.
    """

    start_global = time.perf_counter()

    # Remet le compteur SQL à zéro
    from django.db import connection
    connection.queries_log.clear()

    maintenant = timezone.now()

    # =================================================================
    # 1. GESTION DES FILTRES ET DES DATES
    # =================================================================
    recherche = request.GET.get('q', '')
    categorie_id = request.GET.get('categorie')
    mois_filtre = int(request.GET.get('mois', maintenant.month))
    annee_filtre = int(request.GET.get('annee', maintenant.year))

    # ⚡ Récupération du critère de tri depuis l'URL (Défaut: 'nom')
    tri_choisi = request.GET.get('tri', 'nom')

    est_mois_en_cours = (mois_filtre == maintenant.month and annee_filtre == maintenant.year)

    mois_prec = 12 if mois_filtre == 1 else mois_filtre - 1
    annee_prec = annee_filtre - 1 if mois_filtre == 1 else annee_filtre
    mois_suivant, annee_suivante = (1, annee_filtre + 1) if mois_filtre == 12 else (mois_filtre + 1, annee_filtre)

    # ⚡ On applique le tri directement via le manager d'inventaire
    produits_queryset = Produit.objects.select_related('categorie').filter(actif=True).classer_selon_critere(
        critere=tri_choisi,
        mois=mois_filtre,
        annee=annee_filtre
    )

    if recherche:
        produits_queryset = produits_queryset.filter(Q(nom__icontains=recherche) | Q(code__icontains=recherche))
    if categorie_id:
        produits_queryset = produits_queryset.filter(categorie_id=categorie_id)

    page_number = request.GET.get('page', 1)

    # Initialisation des variables des totaux globaux
    valeur_initiale_totale_reelle = Decimal('0')
    valeur_initiale_totale_theorique = Decimal('0')
    valeur_totale_inventaire_actuelle = Decimal('0')
    valeur_totale_theorique_actuelle = Decimal('0')

    # Dates de début et de fin de mois pour les requêtes
    debut_mois = timezone.make_aware(datetime(annee_filtre, mois_filtre, 1))
    fin_mois = debut_mois + relativedelta(months=1)

    debut_mois_prec = timezone.make_aware(datetime(annee_prec, mois_prec, 1))
    fin_mois_prec = debut_mois_prec + relativedelta(months=1)

    # ============================================================================
    # PRECHARGEMENT DES FICHES TECHNIQUES ET DICTIONNAIRES (Pour calculs locaux)
    # ============================================================================
    ventes_par_service = (
        PaiementEmploye.objects
        .filter(date_paiement__gte=debut_mois, date_paiement__lt=fin_mois)
        .values("services")
        .annotate(nb_ventes=Count("id"))
    )
    ventes_dict = {ligne["services"]: ligne["nb_ventes"] for ligne in ventes_par_service}

    recettes = (
        ConsommableService.objects
        .select_related("service", "produit")
        .only("service_id", "produit_id", "quantite_prevue")
    )

    conso_theorique_dict = defaultdict(Decimal)
    for recette in recettes:
        nb_ventes = ventes_dict.get(recette.service_id, 0)
        conso_theorique_dict[recette.produit_id] += (recette.quantite_prevue * nb_ventes)

    # =================================================================
    # 2. BRANCHE A : CALCULS EN BASE DE DONNÉES (MOIS EN COURS)
    # =================================================================
    if est_mois_en_cours:
        # Analyse des ventes et fiches techniques
        ventes_services_sub = PaiementEmploye.objects.filter(
            services__id=OuterRef('service_id'),
            date_paiement__gte=debut_mois,
            date_paiement__lt=fin_mois
        ).values('services__id').annotate(cnt=Count('id')).values('cnt')

        conso_theo_sub = ConsommableService.objects.filter(
            produit_id=OuterRef('pk')
        ).annotate(
            nb_ventes=Coalesce(Subquery(ventes_services_sub[:1]), 0)
        ).annotate(
            total_conso=ExpressionWrapper(F('quantite_prevue') * F('nb_ventes'), output_field=DecimalField(max_digits=10, decimal_places=2))
        ).values('produit_id').annotate(total_global=Sum('total_conso')).values('total_global')

        # Flux (Entrées / Inventaires manuels)
        entrees_sub = MouvementStock.objects.filter(
            produit_id=OuterRef('pk'), type_mouvement='ENTREE',
            date_mouvement__gte=debut_mois, date_mouvement__lt=fin_mois, date_mouvement__year=annee_filtre
        ).values('produit_id').annotate(total=Sum('quantite')).values('total')

        sorties_inv_sub = MouvementStock.objects.filter(
            produit_id=OuterRef('pk'), type_mouvement='SORTIE', is_automatique=False,
            date_mouvement__gte=debut_mois, date_mouvement__lt=fin_mois, date_mouvement__year=annee_filtre
        ).order_by('-date_mouvement').values('quantite')

        snap_courant_sub = StockMensuelSnapshot.objects.filter(produit_id=OuterRef('pk'), mois=mois_filtre, annee=annee_filtre)

        # Annotation finale avec isolation des produits créés ce mois-ci
        produits_finaux = produits_queryset.annotate(
            pamp_final=Coalesce(F('prix_achat_moyen'), Decimal('0')),
            total_entrees=Coalesce(Subquery(entrees_sub[:1]), Decimal('0')),
            total_conso_theo_brute=Coalesce(Subquery(conso_theo_sub[:1]), Decimal('0')),
            inventaire_physique=Subquery(sorties_inv_sub[:1]),
        ).annotate(
            # 🔥 SÉCURITÉ : Forçage à 0 si le produit est créé au cours de ce mois
            debut_mois_reel=Case(
                When(created_at__month=mois_filtre, created_at__year=annee_filtre, then=Value(Decimal('0'))),
                default=Coalesce(Subquery(snap_courant_sub.values('quantite_initiale_reelle')[:1]), Decimal('0')),
                output_field=DecimalField(max_digits=10, decimal_places=2)
            ),
            debut_mois_theo=Case(
                When(created_at__month=mois_filtre, created_at__year=annee_filtre, then=Value(Decimal('0'))),
                default=Coalesce(Subquery(snap_courant_sub.values('quantite_initiale_theorique')[:1]), Decimal('0')),
                output_field=DecimalField(max_digits=10, decimal_places=2)
            ),
        ).annotate(
            stock_final_reel=F('quantite_stock')
        ).annotate(
            conso_reelle_carburant=ExpressionWrapper(
                (F('debut_mois_reel') + F('total_entrees')) - F('stock_final_reel'),
                output_field=DecimalField(max_digits=10, decimal_places=2)
            )
        ).annotate(
            total_conso_theo=Case(
                When(est_carburant=True, then=Case(
                    When(conso_reelle_carburant__lt=0, then=Decimal('0')),
                    default=F('conso_reelle_carburant')
                )),
                default=F('total_conso_theo_brute'),
                output_field=DecimalField(max_digits=10, decimal_places=2)
            )
        ).annotate(
            stock_final_theorique=ExpressionWrapper(
                F('debut_mois_theo') + F('total_entrees') - F('total_conso_theo'),
                output_field=DecimalField(max_digits=10, decimal_places=2)
            )
        ).annotate(
            valeur_debut_mois_reel=ExpressionWrapper(F('debut_mois_reel') * F('pamp_final'), output_field=DecimalField(max_digits=12, decimal_places=2)),
            valeur_debut_mois_theo=ExpressionWrapper(F('debut_mois_theo') * F('pamp_final'), output_field=DecimalField(max_digits=12, decimal_places=2)),
            valeur_actuelle_reelle=ExpressionWrapper(F('stock_final_reel') * F('pamp_final'), output_field=DecimalField(max_digits=12, decimal_places=2)),
            valeur_actuelle_theorique=ExpressionWrapper(F('stock_final_theorique') * F('pamp_final'), output_field=DecimalField(max_digits=12, decimal_places=2)),
            ecart_stock_actuel=ExpressionWrapper(F('stock_final_theorique') - F('stock_final_reel'), output_field=DecimalField(max_digits=10, decimal_places=2)),
            ecart_financier_actuel=ExpressionWrapper(
                F('valeur_actuelle_theorique') - F('valeur_actuelle_reelle'),
                output_field=DecimalField(max_digits=12, decimal_places=2)
            )
        )

        produits_finaux = list(produits_finaux)

        # Calcul des totaux globaux en mémoire Python (plus sûr avec les annotations)
        valeur_initiale_totale_reelle = sum((p.valeur_debut_mois_reel or Decimal("0")) for p in produits_finaux)
        valeur_initiale_totale_theorique = sum((p.valeur_debut_mois_theo or Decimal("0")) for p in produits_finaux)
        valeur_totale_inventaire_actuelle = sum((p.valeur_actuelle_reelle or Decimal("0")) for p in produits_finaux)
        valeur_totale_theorique_actuelle = sum((p.valeur_actuelle_theorique or Decimal("0")) for p in produits_finaux)

        has_results = produits_queryset.exists()

        paginator = Paginator(produits_finaux, 15)
        try:
            produits_pagines = paginator.page(page_number)
        except PageNotAnInteger:
            produits_pagines = paginator.page(1)
        except EmptyPage:
            produits_pagines = paginator.page(paginator.num_pages)

    # =================================================================
    # 3. BRANCHE B : HISTORIQUE COMPATIBLE (MOIS PASSÉS)
    # =================================================================
    else:
        produits_ids_filtered = produits_queryset.values_list('id', flat=True)

        totaux_snapshots = StockMensuelSnapshot.objects.filter(
            mois=mois_filtre, annee=annee_filtre, produit_id__in=produits_ids_filtered
        ).aggregate(
            v_init_reel=Sum(F('quantite_initiale_reelle') * Coalesce(F('pamp_historique'), Decimal('0'))),
            v_init_theo=Sum(F('quantite_initiale_theorique') * Coalesce(F('pamp_historique'), Decimal('0'))),
            v_act_reel=Sum(F('quantite_finale_reelle') * Coalesce(F('pamp_historique'), Decimal('0'))),
            v_act_theo=Sum(F('quantite_finale_theorique') * Coalesce(F('pamp_historique'), Decimal('0')))
        )

        valeur_initiale_totale_reelle = totaux_snapshots['v_init_reel'] or Decimal('0')
        valeur_initiale_totale_theorique = totaux_snapshots['v_init_theo'] or Decimal('0')
        valeur_totale_inventaire_actuelle = totaux_snapshots['v_act_reel'] or Decimal('0')
        valeur_totale_theorique_actuelle = totaux_snapshots['v_act_theo'] or Decimal('0')

        has_results = produits_queryset.exists()

        paginator = Paginator(produits_queryset, 15)
        try:
            produits_pagines = paginator.page(page_number)
        except PageNotAnInteger:
            produits_pagines = paginator.page(1)
        except EmptyPage:
            produits_pagines = paginator.page(paginator.num_pages)

        produits_page_ids = [p.id for p in produits_pagines.object_list]

        snapshots_mois = StockMensuelSnapshot.objects.filter(mois=mois_filtre, annee=annee_filtre, produit_id__in=produits_page_ids)
        map_snapshots = {s.produit_id: s for s in snapshots_mois}

        snapshots_suivants = StockMensuelSnapshot.objects.filter(mois=mois_suivant, annee=annee_suivante, produit_id__in=produits_page_ids)
        map_snapshots_suivant = {ss.produit_id: ss for ss in snapshots_suivants}

        dernier_mv_subquery = MouvementStock.objects.filter(
            produit_id=OuterRef('produit_id'), date_mouvement__month=mois_filtre, date_mouvement__year=annee_filtre, pamp_historique__isnull=False
        ).order_by('-date_mouvement').values('pamp_historique')[:1]

        mouvements_du_mois = MouvementStock.objects.filter(
            date_mouvement__month=mois_filtre, date_mouvement__year=annee_filtre, produit_id__in=produits_page_ids
        ).annotate(dernier_pamp=Subquery(dernier_mv_subquery)).values('produit_id', 'dernier_pamp').distinct()

        map_pamp_historique = {item['produit_id']: item['dernier_pamp'] for item in mouvements_du_mois}

        entrees_aggregations = MouvementStock.objects.filter(
            type_mouvement='ENTREE', date_mouvement__month=mois_filtre, date_mouvement__year=annee_filtre, produit_id__in=produits_page_ids
        ).values('produit_id').annotate(total=Sum('quantite'))
        map_entrees = {item['produit_id']: item['total'] for item in entrees_aggregations}

        sorties_inventaires = MouvementStock.objects.filter(
            type_mouvement='SORTIE', is_automatique=False, date_mouvement__month=mois_filtre, date_mouvement__year=annee_filtre, produit_id__in=produits_page_ids
        ).order_by('produit_id', 'date_mouvement')
        map_sorties_inventaires = {s.produit_id: s.quantite for s in sorties_inventaires}

        # Construction locale pour l'historique passé
        for p in produits_pagines.object_list:
            snap = map_snapshots.get(p.id)
            est_carb = getattr(p, 'est_carburant', False)
            entrees_mois = map_entrees.get(p.id, Decimal('0'))

            if snap and getattr(snap, 'pamp_historique', None):
                pamp = snap.pamp_historique
            else:
                pamp = map_pamp_historique.get(p.id) or Decimal('0')

            p.pamp_final = pamp

            # Sécurité historique : Déterminer la date de début du mois de consultation
            ref_date = timezone.make_aware(datetime(annee_filtre, mois_filtre, 1))

            if snap:
                p.debut_mois_reel = snap.quantite_initiale_reelle
                p.debut_mois_theo = snap.quantite_initiale_theorique
                p.stock_final_reel = snap.quantite_finale_reelle
                p.stock_final_theorique = snap.quantite_finale_theorique if est_carb else (p.debut_mois_theo + entrees_mois - (snap.quantite_initiale_theorique + entrees_mois - snap.quantite_finale_theorique))
                p.total_conso_theo = (p.debut_mois_reel + entrees_mois) - p.stock_final_reel if est_carb else (snap.quantite_initiale_theorique + entrees_mois - snap.quantite_finale_theorique)
            else:
                # 🔥 SÉCURITÉ HISTORIQUE : Si le produit a été créé APRES le mois consulté, ou qu'il n'existait pas : 0 absolu
                p.debut_mois_reel = Decimal('0')
                p.debut_mois_theo = Decimal('0')
                if p.created_at > ref_date + relativedelta(months=1):
                    p.stock_final_reel = Decimal('0')
                else:
                    snap_suiv = map_snapshots_suivant.get(p.id)
                    p.stock_final_reel = snap_suiv.quantite_initiale_reelle if snap_suiv else map_sorties_inventaires.get(p.id, entrees_mois)
                
                p.stock_final_theorique = p.stock_final_reel if est_carb else (p.debut_mois_theo + entrees_mois)
                p.total_conso_theo = Decimal('0')

            p.valeur_debut_mois_reel = p.debut_mois_reel * pamp
            p.valeur_debut_mois_theo = p.debut_mois_theo * pamp
            p.valeur_actuelle_reelle = p.stock_final_reel * pamp
            p.valeur_actuelle_theorique = p.stock_final_theorique * pamp
            p.ecart_stock_actuel = p.stock_final_theorique - p.stock_final_reel
            p.ecart_financier_actuel = p.valeur_actuelle_theorique - p.valeur_actuelle_reelle

    # =================================================================
    # 4. RENDU CONTEXTE
    # =================================================================
    context = {
        'produits': produits_pagines,
        'categories': CategorieProduit.objects.all(),
        'has_results': has_results,
        'valeur_totale': valeur_totale_inventaire_actuelle,
        'valeur_totale_theorique': valeur_totale_theorique_actuelle,
        'ecart_financier_global': valeur_totale_theorique_actuelle - valeur_totale_inventaire_actuelle,
        'valeur_initiale_totale_reelle': valeur_initiale_totale_reelle,
        'valeur_initiale_totale_theorique': valeur_initiale_totale_theorique,
        'ecart_initial_global': valeur_initiale_totale_theorique - valeur_initiale_totale_reelle,
        'mois_actuel': mois_filtre,
        'annee_actuelle': annee_filtre,
        'q': recherche,
        'categorie_selectionnee': categorie_id,
        'tri_actuel': tri_choisi,
    }

    # === LIGNES DE DEBUG À AJOUTER TEMPORAIREMENT ===
    for prod in produits_pagines.object_list:
        if prod.nom == "para": 
            print(f"--- DEBUG {prod.nom} ---")
            print(f"Début de mois réel (Python): {prod.debut_mois_reel}")
            print(f"Stock en BDD (quantite_stock): {prod.quantite_stock}")
    # ===============================================

    return render(request, 'inventaire/liste_produits.html', context)




@gerant_only
def detail_produit_bi(request, produit_id):
    """
    Vue BI détaillée BEL'R.
    Calcule l'historique exact, les coûts réels/théoriques globaux et isole
    la logique comptable du carburant pour éviter les écarts clients fantômes.
    """
    produit = get_object_or_404(Produit, pk=produit_id)
    maintenant = timezone.now()

    # 1. Filtres et initialisations
    mois_filtre = int(request.GET.get('mois', maintenant.month))
    annee_filtre = int(request.GET.get('annee', maintenant.year))

    est_mois_en_cours = (mois_filtre == maintenant.month and annee_filtre == maintenant.year)

    # ------------------------------------------------------------------
    # 🔐 CLOISONNEMENT STRICT DU PAMP (DANS SON COIN SANS TOUCHER AU RESTE)
    # ------------------------------------------------------------------
    if mois_filtre == maintenant.month and annee_filtre == maintenant.year:
        pamp = produit.prix_achat_moyen or Decimal('0')
    else:
        # On fait une requête locale rapide ISOLÉE pour le PAMP passé
        snap_pamp = StockMensuelSnapshot.objects.filter(
            produit=produit, mois=mois_filtre, annee=annee_filtre
        ).first()

        if snap_pamp and snap_pamp.pamp_historique:
            pamp = snap_pamp.pamp_historique
        else:
            dernier_mouv_pamp = MouvementStock.objects.filter(
                produit=produit,
                date_mouvement__month=mois_filtre,
                date_mouvement__year=annee_filtre,
                pamp_historique__isnull=False
            ).order_by('-date_mouvement').first()
            pamp = dernier_mouv_pamp.pamp_historique if dernier_mouv_pamp else Decimal('0')
    # ------------------------------------------------------------------

    # Détection de la nature du produit (Exception Carburant)
    est_carburant = getattr(produit, 'est_carburant', False)

    services_ids = ConsommableService.objects.filter(produit=produit).values_list('service_id', flat=True)
    premier_jour_mois = date(annee_filtre, mois_filtre, 1)

    # --- CALCUL DU STOCK INITIAL EN DÉBUT DE MOIS ---
    mois_prec = 12 if mois_filtre == 1 else mois_filtre - 1
    annee_prec = annee_filtre - 1 if mois_filtre == 1 else annee_filtre

    # 🔥 SÉCURITÉ ABSOLUE : Si le produit a été créé ce mois-ci, son stock initial au 1er est forcément de 0
    if produit.created_at.month == mois_filtre and produit.created_at.year == annee_filtre:
        stock_debut_mois = Decimal('0')
        stock_debut_mois_theo = Decimal('0')
    else:
        stock_init = StockMensuelSnapshot.objects.filter(
            produit=produit, mois=mois_filtre, annee=annee_filtre
        ).first()

        if stock_init:
            stock_debut_mois = stock_init.quantite_initiale_reelle
            stock_debut_mois_theo = stock_init.quantite_initiale_reelle if est_carburant else stock_init.quantite_initiale_theorique
        else:
            stock_debut_mois = Decimal('0')
            stock_debut_mois_theo = Decimal('0')

    # 2. Données brutes du mois filtré
    mouvements_mois = MouvementStock.objects.filter(
        produit=produit, date_mouvement__month=mois_filtre, date_mouvement__year=annee_filtre
    )
    entrees_mois = mouvements_mois.filter(type_mouvement='ENTREE').aggregate(s=Sum('quantite'))['s'] or Decimal('0')

    # --- CALCUL DE LA CONSOMMATION MANUELLE VIA STOCK RESTANT ---
    mouvement_restant = mouvements_mois.filter(
        type_mouvement='SORTIE',
        is_automatique=False
    ).order_by('-date_mouvement').first()

    if m_restant := mouvement_restant:
        if est_mois_en_cours:
            stock_reel = produit.quantite_stock
        else:
            stock_reel = m_restant.quantite

        conso_reelle = (stock_debut_mois + entrees_mois) - stock_reel
        if conso_reelle < 0:
            conso_reelle = Decimal('0')
    else:
        conso_reelle = Decimal('0')
        if est_mois_en_cours:
            stock_reel = produit.quantite_stock
        else:
            stock_reel = stock_debut_mois + entrees_mois

    conso_manuelle = conso_reelle

    # --- 3. LOGIQUE DE CALCUL UNIQUE ---
    if est_carburant:
        ventes_liees = PaiementEmploye.objects.none()
        nb_prestations = 0
        ca_services_lies = Decimal('0')
        recettes = ConsommableService.objects.none()

        conso_theo = conso_reelle
        stock_theorique = stock_reel
        conso_theo_prec = Decimal('0')
        conso_manuelle_prec = Decimal('0')
        nb_prestations_prec = 0
    else:
        ventes_liees = PaiementEmploye.objects.filter(
            services__id__in=services_ids,
            date_paiement__month=mois_filtre,
            date_paiement__year=annee_filtre
        ).distinct()

        nb_prestations = ventes_liees.count()
        ca_services_lies = ventes_liees.aggregate(s=Sum('total_services'))['s'] or Decimal('0')

        conso_theo = Decimal('0')
        recettes = ConsommableService.objects.filter(produit=produit).select_related('service')

        for r in recettes:
            nb_ventes_serv = ventes_liees.filter(services=r.service).count()

            # Calcul de la consommation théorique
            conso_theo += r.quantite_prevue * nb_ventes_serv

            # 🌟 FIXATION DU DOSAGE VISUEL UNIQUE : On détermine la valeur à afficher pour ce mois
            if est_mois_en_cours:
                r.dosage_bi_affiche = r.quantite_prevue
            else:
                hist = DosageHistorique.objects.filter(
                    produit=produit, service=r.service, mois=mois_filtre, annee=annee_filtre
                ).first()
                r.dosage_bi_affiche = hist.quantite_figee if hist else r.quantite_prevue

        stock_theorique = stock_debut_mois_theo + entrees_mois - conso_theo

        mouv_prec = MouvementStock.objects.filter(produit=produit, date_mouvement__month=mois_prec, date_mouvement__year=annee_prec)
        ventes_liees_prec = PaiementEmploye.objects.filter(
            services__id__in=services_ids, date_paiement__month=mois_prec, date_paiement__year=annee_prec
        ).distinct()

        conso_theo_prec = Decimal('0')
        for r in recettes:
            nb_ventes_serv_prec = ventes_liees_prec.filter(services=r.service).count()
            conso_theo_prec += r.quantite_prevue * nb_ventes_serv_prec

        # 🔥 SÉCURITÉ SUR LE MOIS PRÉCÉDENT : Si le produit a été créé après ou pendant le mois M-1
        if produit.created_at.month == mois_prec and produit.created_at.year == annee_prec:
            base_r_prec = Decimal('0')
        else:
            stock_init_m_prec = StockMensuelSnapshot.objects.filter(produit=produit, mois=mois_prec, annee=annee_prec).first()
            base_r_prec = stock_init_m_prec.quantite_initiale_reelle if stock_init_m_prec else Decimal('0')
            
        entrees_m_prec = mouv_prec.filter(type_mouvement='ENTREE').aggregate(s=Sum('quantite'))['s'] or Decimal('0')
        restant_m_prec = mouv_prec.filter(type_mouvement='SORTIE', is_automatique=False).first()

        conso_manuelle_prec = (base_r_prec + entrees_m_prec - restant_m_prec.quantite) if restant_m_prec else Decimal('0')
        if conso_manuelle_prec < 0:
            conso_manuelle_prec = Decimal('0')
        nb_prestations_prec = ventes_liees_prec.count()

    # --- 4. VALORISATIONS ET FINANCES DE PÉRIODE ---
    if est_carburant:
        impact_reel = conso_reelle * pamp
        impact_theo = impact_reel
        prorata_reel = (impact_reel / ca_services_lies * 100) if ca_services_lies > 0 else 0
        prorata_theo = prorata_reel
    else:
        impact_theo = conso_theo * pamp
        impact_reel = conso_reelle * pamp
        prorata_theo = (impact_theo / ca_services_lies * 100) if ca_services_lies > 0 else 0
        prorata_reel = (impact_reel / ca_services_lies * 100) if ca_services_lies > 0 else 0

    ecart_impact = impact_reel - impact_theo
    ecart_conso_brut = (conso_theo - conso_reelle)

    for r in recettes:
        nb_ventes_serv = ventes_liees.filter(services=r.service).count()
        # On utilise le dosage fixé pour valoriser correctement le tableau du bas passé
        r.cout_mensuel_total = (r.dosage_bi_affiche * pamp) * nb_ventes_serv
        r.prorata_individuel = (r.cout_mensuel_total / ca_services_lies * 100) if ca_services_lies > 0 else 0

    def calc_evo(act, pre):
        if pre == 0:
            return 100 if act > 0 else 0
        return ((act - pre) / pre) * 100

    evo_conso_theo_prec = calc_evo(conso_theo, conso_theo_prec)

    # --- 7. RE-TRAITEMENT ET STABILISATION DE L'HISTORIQUE ---
    historique = mouvements_mois.order_by('-date_mouvement').select_related('created_by')
    for mv in historique:
        if mv.type_mouvement == 'ENTREE':
            mv.prix_total_achat = mv.quantite * (mv.prix_achat_unitaire or pamp)
            mv.quantite_a_afficher = mv.quantite
        elif mv.type_mouvement == 'SORTIE':
            if mv.is_automatique:
                mv.quantite_a_afficher = mv.quantite
            else:
                conso_calculee = mv.quantite_avant - mv.quantite
                mv.quantite_a_afficher = conso_calculee if conso_calculee >= 0 else Decimal('0')
        else:
            mv.quantite_a_afficher = mv.quantite

    # 8. Dispatch global vers le template
    context = {
        'produit': produit,
        'recettes': recettes,
        'nb_prestations': nb_prestations,
        'conso_theo': conso_theo,
        'conso_manuelle': conso_manuelle,
        'conso_reelle': conso_reelle,
        'ecart_conso_brut': ecart_conso_brut,
        'evo_conso_theo_prec': evo_conso_theo_prec,
        'stock_debut_mois': stock_debut_mois,
        'stock_theorique': stock_theorique,
        'stock_reel': stock_reel,
        'valeur_stock': stock_reel * pamp,
        'impact_reel': impact_reel,
        'ecart_impact': ecart_impact,
        'prorata_theo': prorata_theo,
        'prorata_reel': prorata_reel,
        'evo_service': calc_evo(nb_prestations, nb_prestations_prec),
        'evo_manuelle': calc_evo(conso_manuelle, conso_manuelle_prec),
        'historique_mois': historique,
        'mois_actuel': mois_filtre,
        'annee_actuel': annee_filtre,
        'est_carburant': est_carburant,
    }
    return render(request, 'inventaire/detail_produit.html', context)