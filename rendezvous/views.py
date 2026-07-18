
# # Create your views here.


def calendrier(request):
    """Vue calendrier"""
    employe_id = request.GET.get('employe')
    date_str = request.GET.get('date')
    
    if date_str:
        try:
            selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except:
            selected_date = date.today()
    else:
        selected_date = date.today()
    
    context = {
        'selected_date': selected_date,
        'employe_id': employe_id,
    }
    return render(request, 'rendezvous/calendrier.html', context)


# # gestion/views.py
# from django.shortcuts import render
# from authentification.decorator import employe_required
# from .models import RecuClient




# # gestion/views.py
# from django.shortcuts import render
# from django.contrib.auth.decorators import login_required
# from django.db.models import Q, Sum
# from django.utils import timezone
# from datetime import datetime
# from .models import RecuClient,RecuSupprimeLog
from django.contrib.auth.models import User

# ==========================================
# 1. Standard Library Imports
# ==========================================
import datetime
from datetime import date, timedelta
from decimal import Decimal
import json
import random
import uuid

# ==========================================
# 2. Django Core Imports
# ==========================================
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import models, transaction
from django.db.models import Count, F, Prefetch, Q, Sum, Value
from django.db.models.functions import Coalesce, TruncDay  # Vérifié et inclus
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST  # Vérifié et inclus

# ==========================================
# 3. Local Apps Imports (Rôles & Autres Apps)
# ==========================================
from authentification.decorator import employe_required, gerant_only, manager_required, manager_only_strict
from clients.models import Client
from employes.models import Employe
from gestion.models import CategorieService, Service

# ==========================================
# 4. App-Local Imports (Formulaires & Modèles de l'app actuelle)
# ==========================================
from .forms import PaiementEmployeForm
from .models import PaiementEmploye, RecuClient ,RecuSupprimeLog

# Si tu utilises ta fonction personnalisée pour les reçus dans ce fichier :
# from .utils import generate_numero_recu

# Optionnel : décommente si ta fonction utilitaire est requise ici
# from .utils import generate_numero_recu






@manager_required
def signaler_paiements(request, groupe_id):
    """Permet à l'auteur du paiement de le signaler au gérant une fois le délai dépassé"""
    if request.method == 'POST':
        # On s'assure que seul l'auteur d'origine (ou un gérant) peut déclencher le signalement
        recu = get_object_or_404(RecuClient, numero_groupe=groupe_id, user=request.user)
        
        recu.demande_suppression = True
        recu.save()
        messages.success(request, f"Le reçu {recu.numero_recu} a été signalé au Gérant pour suppression.")
        
    return redirect('paiement_detail', groupe_id=groupe_id) # Redirection sur place pour voir le statut changer



@manager_required

def paiement_delete(request, groupe_id):
    if request.method == 'POST':
        recu = get_object_or_404(RecuClient, numero_groupe=groupe_id)
        
        delai_limite = recu.date + timedelta(minutes=30)
        dans_les_temps = timezone.now() < delai_limite
        
        est_gerant = request.user.groups.filter(name='Gérant').exists() or request.user.is_superuser
        est_auteur = (recu.user is not None and recu.user == request.user)

        autorise = False
        motif_refus = ""

        if dans_les_temps:
            if est_auteur:
                autorise = True
            else:
                motif_refus = "Pendant les 30 premières minutes, seul l'auteur de ce paiement peut effectuer la suppression."
        else:
            if est_gerant:
                if recu.demande_suppression:
                    autorise = True
                else:
                    motif_refus = "Ce paiement n'a pas été formellement signalé pour suppression par le manager ou l'auteur."
            else:
                motif_refus = "Le délai de 30 minutes est dépassé. Vous devez demander au Gérant de supprimer ce reçu signalé."

        if autorise:
            try:
                with transaction.atomic():
                    # 🚨 NOUVEAUTÉ : On enregistre la suppression dans l'historique avant de détruire les données
                    RecuSupprimeLog.objects.create(
                        numero_recu=recu.numero_recu,
                        numero_groupe=recu.numero_groupe,
                        total_global=recu.total_global,
                        supprime_par=request.user
                    )
                    
                    PaiementEmploye.objects.filter(numero_groupe=groupe_id).delete()
                    recu.delete()
                    
                messages.success(request, "La vente et tous les reçus associés ont été supprimés avec succès.")
                return redirect('paiement')
            except Exception as e:
                messages.error(request, f"Erreur lors de la suppression en base de données : {str(e)}")
        else:
            messages.error(request, f"Action refusée : {motif_refus}")
            
    return redirect('paiement_detail', groupe_id=groupe_id)








@manager_required
def historique_paiement(request):  # Ton historique des ventes BEL'R
    # 1. Récupération des filtres depuis la requête GET

    from datetime import datetime
    query_general = request.GET.get('q', '').strip()
    employe_id = request.GET.get('employe', '')
    user_id = request.GET.get('auteur', '')
    date_debut_str = request.GET.get('date_debut', '')
    date_fin_str = request.GET.get('date_fin', '')

    current_user = request.user
    aujourd_hui = timezone.now().date()

    # --- 2. DROITS D'ACCÈS ET CLOISONNEMENT STRICT ---
    if current_user.is_superuser or current_user.groups.filter(name='Gérant').exists():
        ventes = RecuClient.objects.all().order_by('-date')
        est_gerant = True
    else:
        profil_employe = getattr(current_user, 'employe', None)
        if profil_employe:
            ventes = RecuClient.objects.filter(employes=profil_employe).order_by('-date')
        else:
            ventes = RecuClient.objects.none()
        est_gerant = False

    # --- 3. FILTRAGE PAR DATE (Avec exception pour les signalements 🚨) ---
    if date_debut_str or date_fin_str:
        if date_debut_str:
            date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
            ventes = ventes.filter(date__date__gte=date_debut)
        if date_fin_str:
            date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
            ventes = ventes.filter(date__date__lte=date_fin)
    else:
        # FORCE L'AFFICHAGE : Mois en cours OU demande_suppression=True
        premier_jour_mois = aujourd_hui.replace(day=1)
        ventes = ventes.filter(
            Q(date__date__range=[premier_jour_mois, aujourd_hui]) | 
            Q(demande_suppression=True)
        )
        date_debut_str = premier_jour_mois.strftime('%Y-%m-%d')
        date_fin_str = aujourd_hui.strftime('%Y-%m-%d')

    # --- 4. BARRE DE RECHERCHE GLOBALE ---
    if query_general:
        ventes = ventes.filter(
            Q(nom_client__icontains=query_general) | 
            Q(numero_recu__icontains=query_general)
        )

    # --- 5. FILTRES AVANCÉS ---
    if employe_id and est_gerant:
        ventes = ventes.filter(employes__id=employe_id)

    if user_id and est_gerant:
        ventes = ventes.filter(user__id=user_id)

    # --- 6. CALCULS ET COMPTEURS DES TICKETS ---
    ventes_distinctes = ventes.distinct()
    total_tickets = ventes_distinctes.count()
    chiffre_affaire = ventes_distinctes.aggregate(total=Sum('total_global'))['total'] or 0

    # Récupération de la liste des employés (Correction : importation du modèle si nécessaire)
    
    tous_les_employes = Employe.objects.all() if est_gerant else []
    tous_les_auteurs = User.objects.all() if est_gerant else []

    context = {
        'ventes': ventes_distinctes,
        'total_tickets': total_tickets,
        'chiffre_affaire': chiffre_affaire,
        'tous_les_employes': tous_les_employes,
        'tous_les_auteurs': tous_les_auteurs,
        'est_gerant': est_gerant,
        'query_general': query_general,
        'employe_selectionne': employe_id,
        'auteur_selectionne': user_id,
        'date_debut': date_debut_str,
        'date_fin': date_fin_str,
    }

    return render(request, 'rendezvous/list.html', context)




from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q, Sum
from django.utils import timezone
from datetime import datetime

def historique_paiement(request):  # Ton historique des ventes BEL'R
    # 1. Récupération des filtres depuis la requête GET
    query_general = request.GET.get('q', '').strip()
    employe_id = request.GET.get('employe', '')
    user_id = request.GET.get('auteur', '')
    date_debut_str = request.GET.get('date_debut', '')
    date_fin_str = request.GET.get('date_fin', '')
    page = request.GET.get('page', 1)

    current_user = request.user
    aujourd_hui = timezone.now().date()

    # --- 2. DROITS D'ACCÈS ET CLOISONNEMENT STRICT (Tri par date et heure décroissante) ---
    if current_user.is_superuser or current_user.groups.filter(name='Gérant').exists():
        ventes = RecuClient.objects.all().order_by('-date')
        est_gerant = True
    else:
        profil_employe = getattr(current_user, 'employe', None)
        if profil_employe:
            ventes = RecuClient.objects.filter(employes=profil_employe).order_by('-date')
        else:
            ventes = RecuClient.objects.none()
        est_gerant = False

    # --- 3. FILTRAGE PAR DATE (Avec exception pour les signalements 🚨) ---
    if date_debut_str or date_fin_str:
        if date_debut_str:
            date_debut = datetime.strptime(date_debut_str, '%Y-%m-%d').date()
            ventes = ventes.filter(date__date__gte=date_debut)
        if date_fin_str:
            date_fin = datetime.strptime(date_fin_str, '%Y-%m-%d').date()
            ventes = ventes.filter(date__date__lte=date_fin)
    else:
        # FORCE L'AFFICHAGE : Mois en cours OU demande_suppression=True
        premier_jour_mois = aujourd_hui.replace(day=1)
        ventes = ventes.filter(
            Q(date__date__range=[premier_jour_mois, aujourd_hui]) | 
            Q(demande_suppression=True)
        )
        date_debut_str = premier_jour_mois.strftime('%Y-%m-%d')
        date_fin_str = aujourd_hui.strftime('%Y-%m-%d')

    # --- 4. BARRE DE RECHERCHE GLOBALE ---
    if query_general:
        ventes = ventes.filter(
            Q(nom_client__icontains=query_general) | 
            Q(numero_recu__icontains=query_general)
        )

    # --- 5. FILTRES AVANCÉS ---
    if employe_id and est_gerant:
        ventes = ventes.filter(employes__id=employe_id)

    if user_id and est_gerant:
        ventes = ventes.filter(user__id=user_id)

    # Assure l'unicité des résultats après les jointures (Many-to-Many ou ForeignKeys)
    # et ré-applique explicitement l'ordre chronologique inverse complet (date + heure)
    ventes_globales = ventes.distinct().order_by('-date')

    # --- 6. CALCULS ET COMPTEURS DES TICKETS GLOBAUX (Fait directement en BDD) ---
    total_tickets = ventes_globales.count()
    chiffre_affaire = ventes_globales.aggregate(total=Sum('total_global'))['total'] or 0

    # --- 7. PAGINATION (À 20 éléments par page) ---
    paginator = Paginator(ventes_globales, 20)
    try:
        ventes_page = paginator.page(page)
    except PageNotAnInteger:
        # Si la page n'est pas un entier, on livre la première page.
        ventes_page = paginator.page(1)
    except EmptyPage:
        # Si la page est hors limites, on livre la dernière page de résultats.
        ventes_page = paginator.page(paginator.num_pages)

    # Récupération des listes pour les filtres gérant
    tous_les_employes = Employe.objects.all() if est_gerant else []
    tous_les_auteurs = User.objects.all() if est_gerant else []

    context = {
        'ventes': ventes_page,  # Contient uniquement les 20 éléments de la page actuelle
        'total_tickets': total_tickets,  # Statistique globale (recherche incluse)
        'chiffre_affaire': chiffre_affaire,  # Statistique globale (recherche incluse)
        'tous_les_employes': tous_les_employes,
        'tous_les_auteurs': tous_les_auteurs,
        'est_gerant': est_gerant,
        'query_general': query_general,
        'employe_selectionne': employe_id,
        'auteur_selectionne': user_id,
        'date_debut': date_debut_str,
        'date_fin': date_fin_str,
    }

    return render(request, 'rendezvous/list.html', context)






def generate_numero_recu():
    """Génère un numéro de reçu unique type RECU-20260305-A12B"""
    date_str = datetime.datetime.now().strftime('%Y%m%d')
    random_str = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=4))
    return f"RECU-{date_str}-{random_str}"





def paiement_detail(request, groupe_id):
    # On récupère le reçu global sans restreindre l'auteur immédiatement pour laisser le Gérant y accéder
    recu_info = get_object_or_404(RecuClient, numero_groupe=groupe_id)
    
    # ── SÉCURITÉ : Vérification des accès ──
    est_gerant = request.user.groups.filter(name='Gérant').exists() or request.user.is_superuser
    est_auteur = (recu_info.user is not None and recu_info.user == request.user)
    '''
    if not (est_auteur or est_gerant):
        raise PermissionDenied("Vous n'avez pas l'autorisation de consulter cette vente.")'''

    # ── LOGIQUE DU TEMPS IMPARTI ──
    delai_limite = recu_info.date + timedelta(minutes=30)
    dans_les_temps = timezone.now() < delai_limite

    # Récupération des lignes de services associées
    tous_les_services = PaiementEmploye.objects.filter(
        numero_groupe=groupe_id
    ).select_related('employe__user', 'provenance_pack')

    services_simples = []
    packs_groupes = {}

    for p in tous_les_services:
        if p.provenance_pack:
            inst_id = p.pack_instance_id
            if inst_id not in packs_groupes:
                packs_groupes[inst_id] = {
                    'nom': p.provenance_pack.nom,
                    'prix': p.provenance_pack.prix,
                    'details': []
                }
            packs_groupes[inst_id]['details'].append(p)
        else:
            services_simples.append(p)

    stats_employes = tous_les_services.values(
        'employe__user__last_name', 
        'employe__user__first_name'
    ).annotate(ca_partiel=Sum('total_services'))

    context = {
        'recu_info': recu_info,
        'services_simples': services_simples,
        'packs_groupes': packs_groupes.values(),
        'stats_employes': stats_employes,
        'dans_les_temps': dans_les_temps,  # <-- INDISPENSABLE pour ton template HTML
    }
    return render(request, 'rendezvous/detail.html', context)







import uuid
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.db.models import Prefetch
from django.contrib.auth.decorators import login_required


import uuid, json
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages




import json
import uuid
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.db.models import Prefetch
from django.contrib.auth.decorators import login_required

# Importe tes modèles ici

# Importe ta fonction de génération de numéro de reçu si elle est externe
# from .utils import generate_numero_recu 



import json
import uuid
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.db import transaction, models
from django.contrib import messages
from django.db.models import Prefetch





@manager_required
@transaction.atomic
def paiement(request, groupe_id=None):
    """
    Crée ou édite une vente (rendez-vous) pour BEL'R.
    Supporte la proratisation des packs via pack_instance_id.
    """
    instance_recu = None
    if groupe_id:
        # CORRECTION : On récupère globalement sans filtrer sur request.user ici
        # pour pouvoir gérer un message de refus personnalisé plutôt qu'une 404
        instance_recu = get_object_or_404(RecuClient, numero_groupe=groupe_id)

        # ── SÉCURITÉ 1 : VERIFICATION DU TEMPS IMPARTI (30 MIN) ──
        delai_limite = instance_recu.date + timedelta(minutes=30)
        dans_les_temps = timezone.now() < delai_limite
        
        if not dans_les_temps:
            messages.error(request, "Modification impossible : Le délai de 30 minutes est dépassé.")
            return redirect('paiement_detail', groupe_id=groupe_id)

        # ── SÉCURITÉ 2 : VÉRIFICATION DE L'AUTEUR D'ORIGINE ──
        if instance_recu.user != request.user:
            messages.error(request, "Modification refusée : Seul l'auteur de ce ticket peut le modifier.")
            return redirect('paiement_detail', groupe_id=groupe_id)

    if request.method == "POST":
        client_nom = request.POST.get("client_nom", "Client Anonyme")
        mode_paiement = request.POST.get("mode_paiement")
        donnees_prestations = request.POST.get("prestations_json") 

        if not mode_paiement or mode_paiement == "":
            messages.error(request, "Veuillez sélectionner un mode de paiement.")

        elif not donnees_prestations or donnees_prestations == "[]":
            messages.error(request, "Veuillez ajouter au moins une prestation.")
        else:
            try:
                prestations = json.loads(donnees_prestations)
                with transaction.atomic():
                    # 1. Identifiant de groupe (UUID pour les nouveaux, sinon celui existant)
                    current_groupe_id = groupe_id if groupe_id else str(uuid.uuid4())
                    
                    # 2. Nettoyage si édition
                    if groupe_id:
                        PaiementEmploye.objects.filter(numero_groupe=groupe_id).delete()

                    total_global_recu = Decimal('0')
                    employes_du_ticket = [] # <-- CHAÎNON MANQUANT : On prépare une liste pour collecter les employés
                    
                    # 3. Traitement des prestations
                    for item in prestations:
                        emp = get_object_or_404(Employe, id=item['employe_id'])
                        service = get_object_or_404(Service, id=item['service_id'])
                        
                        # Prix envoyé par le JS (déjà proratisé si c'est un pack)
                        montant_final = Decimal(str(item.get('prix_reel', service.prix)))
                        
                        parent_pack = None
                        if item.get('pack_id'):
                            parent_pack = Service.objects.filter(id=item['pack_id']).first()

                        # Création du paiement avec pack_instance_id
                        paiement = PaiementEmploye.objects.create(
                            employe=emp,
                            client_nom=client_nom,
                            numero_groupe=current_groupe_id,
                            total_services=montant_final, 
                            provenance_pack=parent_pack,
                            pack_instance_id=item.get('pack_instance_id'), # Crucial pour les signaux
                            quantite=item.get('quantite', 1),  # <-- AJOUT ICI
                            user=request.user
                        )
                        paiement.services.set([service])
                        total_global_recu += montant_final
                        if emp not in employes_du_ticket:
                            employes_du_ticket.append(emp)

                    # 4. Mise à jour du Reçu Global
                    
                    num_recu = instance_recu.numero_recu if instance_recu else generate_numero_recu()
                    
                    recu, created = RecuClient.objects.update_or_create(
                        numero_groupe=current_groupe_id,
                        defaults={
                            "nom_client": client_nom,
                            "total_global": total_global_recu,
                            "mode_paiement": mode_paiement,
                            "numero_recu": num_recu,
                            "user": request.user
                        }
                    )
                    recu.employes.set(employes_du_ticket)
                
                messages.success(request, f"Vente {'mise à jour' if groupe_id else 'enregistrée'} avec succès !")
                return redirect("paiement_detail", groupe_id=current_groupe_id)

            except json.JSONDecodeError:
                messages.error(request, "Erreur de format des données (JSON).")
            except Exception as e:
                messages.error(request, f"Erreur technique : {str(e)}")



    # ================================================================
    # PARTIE GET : RÉCUPÉRATION DES PRESTATIONS POUR ÉDITION (AJOUT ICI)
    # ================================================================
    prestations_initiales_json = "[]"
    if groupe_id:
        # On récupère tous les paiements liés à ce reçu
        paiements_existants = PaiementEmploye.objects.filter(
            numero_groupe=groupe_id
        ).prefetch_related('services')
        
        liste_prets = []
        for p in paiements_existants:
            # On prend le premier service rattaché au paiement
            srv = p.services.first()
            if srv:
                liste_prets.append({
                    'employe_id': str(p.employe.id),
                    'service_id': str(srv.id),
                    'nom_service': srv.nom,
                    'prix_reel': float(p.total_services),
                    'pack_id': str(p.provenance_pack.id) if p.provenance_pack else None,
                    'pack_instance_id': p.pack_instance_id
                })
        # On transforme la liste en chaîne JSON pour le JS du template
        prestations_initiales_json = json.dumps(liste_prets)

    # --- PARTIE GET (Affichage du formulaire) ---
    # On récupère les catégories avec leurs services actifs uniquement
    categories = CategorieService.objects.prefetch_related(
        Prefetch('service_set', queryset=Service.objects.filter(actif=True), to_attr='actifs')
    ).all()

    context = {
        "categories": categories,
        "employes": Employe.objects.filter(actif=True).select_related('user'),
        "recu_client": instance_recu,
        "is_edit": bool(groupe_id),
        "prestations_initiales": prestations_initiales_json, # <--- TRÈS IMPORTANT
    }

    return render(request, "rendezvous/form.html", context)  





@manager_required
def get_pack_details(request, pack_id):
    # On récupère le service qui est un pack
    pack = get_object_or_404(Service, id=pack_id, est_un_pack=True)
    
    # On prépare la liste des services inclus
    services_inclus = []
    for s in pack.services_inclus.all():
        services_inclus.append({
            'id': s.id,
            'nom': s.nom,
            'prix': float(s.prix)
        })
    
    return JsonResponse({
        'pack_nom': pack.nom,
        'services': services_inclus
    })











