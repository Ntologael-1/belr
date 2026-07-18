
# ==========================================
# 1. Standard Library Imports
# ==========================================
from calendar import monthrange
from datetime import date, datetime, timedelta
from decimal import Decimal
import json

# ==========================================
# 2. Third-Party Imports (dateutil)
# ==========================================
from dateutil.relativedelta import relativedelta

# ==========================================
# 3. Django Core Imports
# ==========================================
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sessions.models import Session
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Avg, Count, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

# ==========================================
# 4. Local Apps Imports (Ajuste selon ton projet)
# ==========================================
from authentification.decorator import employe_required, gerant_only, manager_required
from rendezvous.models import PaiementEmploye

# Importations relatives (si le fichier actuel est dans la même app que ces formulaires/modèles) :
from .forms import EmployeForm, UserForm
from .models import Employe



from django.contrib.auth.decorators import login_required, user_passes_test

def est_gerant(user):
    return user.groups.filter(name='Gerant').exists() or user.is_superuser

@login_required
@user_passes_test(est_gerant)
def reinitialiser_mot_de_passe_employe(request, pk):
    """Permet au gérant de générer un lien de secours si l'employé oublie son mot de passe."""
    employe = get_object_or_404(Employe, pk=pk)
    user = employe.user
    
    # Génération d'un nouveau token valide
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    lien_secours = request.build_absolute_uri(
        reverse('definir_mot_de_passe', kwargs={'uidb64': uid, 'token': token})
    )
    
    return render(request, 'employes/creation_succes.html', {
        'lien': lien_secours, 
        'employe': employe,
        'is_reset': True
    })

@employe_required
def definir_mot_de_passe(request, uidb64, token):
    try:
        # Décoder l'ID de l'utilisateur
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    # Vérifier si le token est valide pour cet utilisateur
    if user is not None and default_token_generator.check_token(user, token):
        if request.method == 'POST':
            mdp = request.POST.get('password')
            confirm_mdp = request.POST.get('confirm_password')
            
            if mdp == confirm_mdp:
                user.set_password(mdp)
                user.is_active = True # Le compte devient fonctionnel
                user.save()
                
                # Connexion automatique après création
                login(request, user)
                messages.success(request, "Votre mot de passe a été configuré avec succès ! Bienvenue chez BEL'R.")
                return redirect('inventaire:liste_produits') # Ou son tableau de bord dédié
            else:
                messages.error(request, "Les mots de passe ne correspondent pas.")
        
        return render(request, 'auth/definir_mot_de_passe.html', {'user': user})
    else:
        return render(request, 'auth/lien_invalide.html')


@employe_required
def custom_password_reset_request(request):
    if request.method == "POST":
        email = request.POST.get('email')
        
        # Sécurité : On cherche l'utilisateur peu importe s'il est actif ou inactif
        users = User.objects.filter(email=email)
        
        if users.exists():
            for user in users:
                # Génération du token secret de récupération
                uid = urlsafe_base64_encode(force_bytes(user.pk))
                token = default_token_generator.make_token(user)
                
                # Construction du lien absolu
                lien_recuperation = request.build_absolute_uri(
                    f"/password-reset/confirm/{uid}/{token}/"
                )
                
                # 1. On l'affiche en gros dans le terminal pour le développeur
                print("\n" + "="*60)
                print(f"🔑 LIEN DE RÉCUPÉRATION POUR {user.username} :")
                print(lien_recuperation)
                print("="*60 + "\n")
                
                # 2. Simulation d'envoi de mail dans la console
                send_mail(
                    subject="Réinitialisation de votre mot de passe - BEL'R",
                    message=f"Bonjour {user.username},\n\nCliquez sur ce lien pour modifier votre mot de passe : {lien_recuperation}",
                    from_email="noreply@belr.com",
                    recipient_list=[user.email],
                    fail_silently=False,
                )
                
                # Pour te faciliter la vie en développement, on passe le lien au template
                # Comme ça, tu peux cliquer dessus directement sur l'écran de succès !
                return render(request, 'auth/password_reset_done.html', {
                    'lien_developpeur': lien_recuperation,
                    'email': email
                })
        else:
            messages.error(request, "Aucun compte n'est associé à cette adresse e-mail.")
            
    return render(request, 'auth/password_reset_form.html')



@manager_required
def regenerer_lien_activation(request, pk):
    """Régénère un lien d'activation unique, l'envoie par mail et permet la copie locale"""
    
    # 1. Sécurité d'accès
    if not request.user.is_staff and not request.user.is_superuser:
        messages.error(request, "Accès refusé.")
        return redirect('employes_list')

    employe = get_object_or_404(Employe, pk=pk)
    user = employe.user

    # 2. Sécurité d'activation
    nom_complet = user.get_full_name().strip() or user.username
    if user.is_active:
        messages.warning(request, f"{nom_complet} a déjà activé son compte.")
        return redirect('employes_list')

    # 3. Calcul du token de sécurité
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    
    # 4. Reconstruction du lien absolu
    lien_activation = request.build_absolute_uri(
        reverse('definir_mot_de_passe', kwargs={'uidb64': uid, 'token': token})
    )

    # 5. Envoi du mail
    if user.email:
        sujet = "BEL'R Salon — Votre lien d'accès collaborateur"
        message_txt = (
            f"Bonjour {user.first_name or user.username},\n\n"
            f"Un nouvel accès a été généré pour votre compte chez BEL'R.\n"
            f"Veuillez configurer votre mot de passe ici :\n{lien_activation}\n\n"
            f"L'équipe BEL'R."
        )
        try:
            send_mail(
                subject=sujet,
                message=message_txt,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
            messages.success(request, f"Le lien a été envoyé par e-mail à {user.email}.")
        except Exception:
            messages.error(request, "Erreur lors de l'envoi du mail, mais le lien est disponible pour copie.")
    else:
        messages.warning(request, "Cet employé n'a pas d'adresse e-mail configurée.")

    # 6. Sauvegarde temporaire en session
    role_name = user.groups.first().name if user.groups.exists() else "Coiffeur"
    request.session['nouveau_lien_valeur'] = lien_activation
    request.session['nouveau_lien_role'] = role_name
    request.session['nouveau_lien_nom'] = nom_complet

    return redirect('employes_list')










@employe_required
def employes_list(request):
    """Liste des employés avec KPIs de performance du mois en cours"""
    today = timezone.now().date()

    # ==========================================
    # GESTION ÉPHÉMÈRE DU LIEN D'ACTIVATION
    # ==========================================
    # Extraction des variables depuis la session
    nouveau_lien = request.session.get('nouveau_lien_valeur', None)
    nouveau_nom = request.session.get('nouveau_lien_nom', None)
    nouveau_role = request.session.get('nouveau_lien_role', None)

    # Nettoyage immédiat pour éviter la réapparition au F5 / rafraîchissement
    if nouveau_lien:
        request.session.pop('nouveau_lien_valeur', None)
        request.session.pop('nouveau_lien_nom', None)
        request.session.pop('nouveau_lien_role', None)

    # ==========================================
    # 1. RÉCUPÉRATION DE LA PÉRIODE (Code original)
    # ==========================================
    try:
        selected_month = int(request.GET.get("month", today.month))
        selected_year = int(request.GET.get("year", today.year))
    except (ValueError, TypeError):
        selected_month, selected_year = today.month, today.year

    month_start = date(selected_year, selected_month, 1)
    _, last_day = monthrange(selected_year, selected_month)
    month_end = date(selected_year, selected_month, last_day)

    # ==========================================
    # 2. FILTRAGE DE BASE & SÉLECTION PAR DÉFAUT (Code original)
    # ==========================================
    employes_qs = (
        Employe.objects.all().select_related("user").order_by("user__last_name")
    )

    # Si 'statut' n'est pas fourni dans l'URL, on force 'actifs' par défaut
    statut = request.GET.get("statut")
    if not statut:
        statut = "actifs"

    # Application du filtre selon le choix de l'utilisateur
    if statut == "actifs":
        employes_qs = employes_qs.filter(actif=True)
    elif statut == "inactifs":
        employes_qs = employes_qs.filter(actif=False)

    # ==========================================
    # 3. CALCUL DES PERFORMANCES (Code original)
    # ==========================================
    paiements_base = PaiementEmploye.objects.filter(
        date_paiement__date__range=[month_start, month_end]
    )

    stats_query = paiements_base.values("employe").annotate(
        ca_genere=Sum("total_services"), nb_actes=Count("id")
    )
    stats_map = {item["employe"]: item for item in stats_query}

    list_with_perf = []
    for emp in employes_qs:
        data = stats_map.get(emp.id, {"ca_genere": 0, "nb_actes": 0})
        ca_emp = float(data["ca_genere"] or 0)

        # Calcul de la rémunération (Bonus + Base)
        bonus = float(emp.calculer_bonus(ca_emp))
        salaire_total = float(emp.salaire_base) + bonus

        list_with_perf.append(
            {
                "info": emp,
                "ca_genere": ca_emp,
                "nb_actes": data["nb_actes"],
                "bonus": bonus,
                "salaire_total": salaire_total,
                "rentabilite": (ca_emp - salaire_total),  # CA généré - Coût employé
            }
        )

    # Tri : les plus performants en premier
    list_with_perf = sorted(
        list_with_perf, key=lambda x: x["ca_genere"], reverse=True
    )

    # ==========================================
    # CONTEXTE ET RENDU (Inclusions éphémères injectées)
    # ==========================================
    context = {
        "employes_perf": list_with_perf,
        "statut": statut,
        "selected_month": selected_month,
        "selected_year": selected_year,
        "months": [(i, date(2000, i, 1).strftime("%B")) for i in range(1, 13)],
        
        # Injection des données du lien d'accès nettoyé
        "lien_valeur": nouveau_lien,
        "lien_nom": nouveau_nom,
        "lien_role": nouveau_role,
    }
    return render(request, "employes/list.html", context)



@login_required
def toggle_employe_status(request, pk):
    if request.method == "POST":
        employe = get_object_or_404(Employe, pk=pk)
        celui_qui_clique = request.user

        # 🔐 SÉCURITÉ 1 : Impossible de s'auto-désactiver
        if employe.user == celui_qui_clique:
            return JsonResponse({
                "status": "denied",
                "message": "Action interdite : Vous ne pouvez pas désactiver votre propre accès."
            }, status=403)

        # 🔐 SÉCURITÉ 2 : Contrôle de la hiérarchie (Un inférieur ne peut pas désactiver un supérieur)
        def obtenir_poids_role(user):
            if user.is_superuser:
                return 4
            if user.groups.filter(name='Gérant').exists():
                return 3
            if user.groups.filter(name='Manager').exists():
                return 2
            return 1  # Coiffeurs, collaborateurs simples, etc.

        poids_acteur = obtenir_poids_role(celui_qui_clique)
        poids_cible = obtenir_poids_role(employe.user)

        # Si la cible a un rang plus élevé ou identique (ex: un manager qui tente de couper un autre manager)
        if poids_cible >= poids_acteur:
            return JsonResponse({
                "status": "denied",
                "message": f"Sécurité : Vous n'avez pas les droits hiérarchiques requis pour modifier le statut de {employe.nom_complet}."
            }, status=403)

        # 1. Inversion du statut de l'employé
        employe.actif = not employe.actif
        employe.save()

        # 2. Synchronisation avec le compte User
        user_cible = employe.user
        user_cible.is_active = employe.actif
        user_cible.save()

        # 3. 🔐 PURGE DES SESSIONS (Oblige tout le personnel non-gérant à se reconnecter)
        sessions_actives = Session.objects.filter(expire_date__gte=timezone.now())
        sessions_a_supprimer = []
        
        for session in sessions_actives:
            data = session.get_decoded()
            user_id_session = data.get('_auth_user_id')
            
            if user_id_session:
                try:
                    u = User.objects.get(id=user_id_session)
                    
                    # CONDITIONS D'EXCLUSION DE LA PURGE :
                    est_gerant = u.is_superuser or u.groups.filter(name='Gérant').exists()
                    est_l_acteur = (u.id == celui_qui_clique.id)
                    
                    if not est_gerant and not est_l_acteur:
                        sessions_a_supprimer.append(session.session_key)
                        
                except User.DoesNotExist:
                    sessions_a_supprimer.append(session.session_key)

        # Suppression groupée et instantanée des sessions en BDD
        if sessions_a_supprimer:
            Session.objects.filter(session_key__in=sessions_a_supprimer).delete()

        # Message personnalisé pour le retour Json
        if employe.actif:
            msg = "Accès activé. Session globale du personnel réinitialisée (Reconnexion requise)."
        else:
            msg = f"Accès révoqué pour {employe.nom_complet}. Session globale réinitialisée."

        return JsonResponse(
            {
                "status": "success",
                "is_active": employe.actif,
                "message": msg,
            }
        )

    return JsonResponse({"status": "error"}, status=400)





@gerant_only
def employe_create(request):
    jours_semaine = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche']

    if request.method == 'POST':
        user_form = UserForm(request.POST)
        employe_form = EmployeForm(request.POST, request.FILES)
        
        if user_form.is_valid() and employe_form.is_valid():
            try:
                # On englobe ABSOLUMENT TOUT dans la transaction
                with transaction.atomic():
                    # 1. Création de l'instance User
                    user = user_form.save(commit=False)
                    user.set_unusable_password() 
                    user.is_active = False       
                    user.save()
                    
                    # 2. Assignation du rôle
                    selected_group = user_form.cleaned_data.get('role')
                    if selected_group:
                        user.groups.add(selected_group)
                    
                    # 3. Création du profil Employé associé
                    employe = employe_form.save(commit=False)
                    employe.user = user
                    employe.actif = False 
                    employe.save()
                
                    # 4. Génération du token et du lien
                    uid = urlsafe_base64_encode(force_bytes(user.pk))
                    token = default_token_generator.make_token(user)
                    lien_activation = request.build_absolute_uri(
                        reverse('definir_mot_de_passe', kwargs={'uidb64': uid, 'token': token})
                    )

                    # 5. On place le RENDER ici ! 
                    # Si le nom du template est faux, Django fait un ROLLBACK immédiat en BDD.
                    return render(request, 'employes/creation_succes.html', {
                        'lien': lien_activation, 
                        'employe': employe
                    })
            
            except Exception as e:
                print(f"--- ERREUR CRÉATION : {e} ---")
                messages.error(request, f"Une erreur technique est survenue : {e}")
    else:
        user_form = UserForm()
        employe_form = EmployeForm()

    return render(request, 'employes/form.html', {
        'user_form': user_form,
        'employe_form': employe_form,
        'jours_semaine': jours_semaine,
        'title': 'Nouvel Employé',
    })

from django.urls import reverse



from django.contrib.auth.decorators import login_required, user_passes_test



@gerant_only
def employe_edit(request, pk):
    """Modifier un employé existant sans écraser ses accès sécurisés"""
    employe = get_object_or_404(Employe, pk=pk)
    
    if request.method == 'POST':
        user_form = UserForm(request.POST, instance=employe.user)
        employe_form = EmployeForm(request.POST, request.FILES, instance=employe)
        
        if user_form.is_valid() and employe_form.is_valid():
            try:
                with transaction.atomic():
                    selected_group = user_form.cleaned_data.get('role')
                    
                    # 🔐 PROTECTION CONTRE L'AUTO-RÉTROGRADATION DU DERNIER GÉRANT
                    if employe.user == request.user:
                        ancien_role_gerant = request.user.groups.filter(name='Gérant').exists()
                        # Si l'utilisateur était gérant et tente de choisir un rôle différent de Gérant
                        if ancien_role_gerant and (not selected_group or selected_group.name != 'Gérant'):
                            # On compte combien d'autres gérants actifs existent en dehors de lui
                            autres_gerants_actifs = User.objects.filter(
                                groups__name='Gérant', 
                                is_active=True
                            ).exclude(id=request.user.id).count()
                            
                            if autres_gerants_actifs == 0:
                                messages.error(
                                    request, 
                                    "Sécurité : Impossible de modifier votre rôle. Vous êtes le seul Gérant actif de l'application."
                                )
                                return redirect('employe_edit', pk=employe.pk)

                    # 1. Mise à jour de l'utilisateur (email, username, etc.)
                    user = user_form.save()
                    
                    # 2. Mise à jour du rôle
                    if selected_group:
                        user.groups.clear()
                        user.groups.add(selected_group)
                    
                    # 3. Mise à jour du profil employé (jours de travail, photo, etc.)
                    employe_form.save()
                    
                    messages.success(request, f"L'employé {employe.user.get_full_name() or employe.user.username} a été mis à jour avec succès.")
                    return redirect('employe_detail', pk=employe.pk)
            
            except Exception as e:
                print(f"--- ERREUR MODIFICATION : {e} ---")
                messages.error(request, f"Une erreur est survenue lors de la modification : {e}")
    else:
        user_form = UserForm(instance=employe.user)
        employe_form = EmployeForm(instance=employe)
    
    context = {
        'user_form': user_form,
        'employe_form': employe_form,
        'employe': employe,
        'jours_semaine': ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi', 'Samedi', 'Dimanche'],
        'title': 'Modifier Employé',
    }
    return render(request, 'employes/form.html', context)


from django.shortcuts import get_object_or_404, render
from django.db.models import Sum, Count
from django.contrib.auth.decorators import login_required, user_passes_test
from calendar import monthrange
from datetime import date
import json
from dateutil.relativedelta import relativedelta
from calendar import monthrange
from datetime import date, timedelta





from decimal import Decimal

@employe_required
def employe_detail(request, pk):
    employe = get_object_or_404(Employe, pk=pk)
    today = date.today()

    # 1. Filtres Temps
    selected_month = int(request.GET.get('month', today.month))
    selected_year = int(request.GET.get('year', today.year))
    month_start = date(selected_year, selected_month, 1)
    month_end = date(selected_year, selected_month, monthrange(selected_year, selected_month)[1])

    # 2. Données de base (Packs inclus via total_services)
    paiements_mois = PaiementEmploye.objects.filter(
        employe=employe,
        date_paiement__date__range=[month_start, month_end]
    )

    agg_base = paiements_mois.aggregate(
        chiffre_affaires=Sum('total_services'),
        nb_paiements=Count('id')
    )
    ca_realise = agg_base['chiffre_affaires'] or 0
    nb_services = paiements_mois.values('services').count()

    # 3. Logique des Paliers (Bonus)
    salaire_fixe = 50000 
    objectif = 300000
    bonus = 0

    if ca_realise >= 500000:
        bonus = ca_realise * Decimal(0.10 ) # 10% si gros CA
    elif ca_realise >= objectif:
        bonus = ca_realise * 0.05  # 5% si objectif atteint

    # 4. Services les plus rentables (Ancienne Stat)
    services_stats = paiements_mois.values(
        'services__id', 'services__nom'
    ).annotate(
        total=Sum('services__prix'),
        count=Count('services')
    ).order_by('-total')[:5]

    # 5. Évolution sur 6 mois (Ancienne Stat)
    date_debut_six_mois = month_start - relativedelta(months=5)
    stats_evolution = PaiementEmploye.objects.filter(
        date_paiement__date__range=[date_debut_six_mois, month_end]
    ).values('date_paiement__date__year', 'date_paiement__date__month', 'employe').annotate(
        total_ca=Sum('total_services')
    )

    evolution_data = []
    for i in range(5, -1, -1):
        d = month_start - relativedelta(months=i)
        ca_emp = sum(x['total_ca'] for x in stats_evolution 
                     if x['date_paiement__date__month'] == d.month 
                     and x['date_paiement__date__year'] == d.year 
                     and x['employe'] == employe.id)
        
        ca_tous = [x['total_ca'] for x in stats_evolution 
                   if x['date_paiement__date__month'] == d.month 
                   and x['date_paiement__date__year'] == d.year]
        moy_salon = sum(ca_tous) / len(ca_tous) if ca_tous else 0

        evolution_data.append({
            'mois': d.strftime('%b %Y'),
            'employe': float(ca_emp),
            'moyenne': float(moy_salon)
        })

    # 6. Classement
    classement = PaiementEmploye.objects.filter(
        date_paiement__date__range=[month_start, month_end]
    ).values('employe__id', 'employe__user__first_name').annotate(
        total=Sum('total_services')
    ).order_by('-total')

    position = next((i for i, x in enumerate(classement, 1) if x['employe__id'] == employe.id), 0)

    context = {
        'employe': employe,
        'selected_month': selected_month,
        'selected_year': selected_year,
        'years': range(today.year - 3, today.year + 1),
        'months': [(i, date(2000, i, 1).strftime('%B')) for i in range(1, 13)],
        'stats': {
            'chiffre_affaires': ca_realise,
            'nb_paiements': agg_base['nb_paiements'] or 0,
            'nb_services': nb_services,
            'salaire_fixe': salaire_fixe,
            'bonus': bonus,
            'net_a_payer': salaire_fixe + bonus
        },
        'services_stats': services_stats,
        'evolution_json': json.dumps(evolution_data),
        'position': position,
        'objectif': objectif,
        'progression': round((ca_realise / objectif * 100), 1) if objectif > 0 else 0,
    }
    return render(request, 'employes/detail.html', context)




@employe_required
def tableau_bord_coiffeur(request):
    if not hasattr(request.user, 'employe'):
        messages.error(request, "Accès réservé aux employés.")
        return redirect('dashboard')

    employe = request.user.employe
    today = date.today()

    # 1. Filtres
    selected_month = int(request.GET.get('month', today.month))
    selected_year = int(request.GET.get('year', today.year))
    month_start = date(selected_year, selected_month, 1)
    month_end = date(selected_year, selected_month, monthrange(selected_year, selected_month)[1])

    # 2. CA Actuel (Packs inclus)
    paiements_mois = PaiementEmploye.objects.filter(
        employe=employe,
        date_paiement__date__range=[month_start, month_end]
    )
    stats_agg = paiements_mois.aggregate(ca=Sum('total_services'), count=Count('services'))
    ca_actuel = stats_agg['ca'] or 0

    # 3. Rémunération par paliers
    salaire_fixe = 50000
    objectif_ca = 300000
    bonus = 0
    if ca_actuel >= 500000:
        bonus = ca_actuel * 0.10
    elif ca_actuel >= objectif_ca:
        bonus = ca_actuel * 0.05

    # 4. Évolution (6 derniers mois)
    evolution_data = []
    for i in range(5, -1, -1):
        m = (selected_month - i - 1) % 12 + 1
        y = selected_year + (selected_month - i - 1) // 12
        m_start = date(y, m, 1)
        m_end = date(y, m, monthrange(y, m)[1])
        
        total_m = PaiementEmploye.objects.filter(
            employe=employe, date_paiement__date__range=[m_start, m_end]
        ).aggregate(total=Sum('total_services'))['total'] or 0
        
        evolution_data.append({'mois': m_start.strftime('%b %Y'), 'total': float(total_m)})

    # 5. Services les plus réalisés (Ancienne Stat)
    services_rentables_qs = paiements_mois.values('services__nom').annotate(
        total=Sum('services__prix')
    ).order_by('-total')[:5]

    context = {
        'employe': employe,
        'selected_month': selected_month,
        'selected_year': selected_year,
        'stats': {
            'ca_total': ca_actuel,
            'nb_services': stats_agg['count'] or 0,
            'salaire_fixe': salaire_fixe,
            'bonus': bonus,
            'total_revenu': salaire_fixe + bonus
        },
        'evolution_json': json.dumps(evolution_data),
        'progression': round(min((ca_actuel / objectif_ca) * 100, 100), 1) if objectif_ca > 0 else 0,
        'services_rentables_json': json.dumps(list(services_rentables_qs)),
        'derniers_paiements': paiements_mois.prefetch_related('services').order_by('-date_paiement')[:10],
    }
    return render(request, 'employes/dashboard_coiffeur.html', context)