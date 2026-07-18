# authentication/decorators.py
# authentication/decorators.py
from functools import wraps
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.http import JsonResponse

# ==========================================
#  1. TES FONCTIONS DE TEST (CONSERVÉES)
# ==========================================

def peut_voir_finance(user):
    """Logique : Admin OU membre du groupe Gérant"""
    return user.is_superuser or user.groups.filter(name='Gérant').exists()

def peut_voir_gestion(user):
    """Logique : Admin, Gérant OU Manager"""
    return user.is_superuser or user.groups.filter(name__in=['Gérant', 'Manager']).exists()

def peut_voir_espace_perso(user):
    """Logique : Tout utilisateur actif"""
    return user.is_active


# ==========================================
#  2. LES DÉCORATEURS INTÉLLIGENTS (REDIRECTION + AJAX)
# ==========================================

# --- VERROU GÉRANT (Niveau Direction) ---
def gerant_only(view_func):
    """Accès : Superutilisateur + Gérant uniquement"""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if peut_voir_finance(request.user):
            return view_func(request, *args, **kwargs)
        
        # Détection si la requête vient du Switch JS (Fetch/AJAX)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'status': 'denied',
                'message': "Action refusée : Cette zone est réservée à la direction."
            }, status=403)
        
        # Redirection classique pour la navigation sur les pages
        messages.error(request, "Accès refusé. Cette zone est réservée à la direction de BEL'R.")
        return redirect('dashboard')  # Remplace par ta route d'accueil si nécessaire
        
    return login_required(_wrapped_view)


# --- VERROU MANAGER (Niveau Supervision) ---
def manager_required(view_func):
    """Accès : Superutilisateur + Gérant + Manager"""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if peut_voir_gestion(request.user):
            return view_func(request, *args, **kwargs)
        
        # Détection si la requête vient du Switch JS (Fetch/AJAX)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'status': 'denied',
                'message': "Action refusée : Vous n'avez pas les droits d'accès requis."
            }, status=403)
        
        # Redirection classique pour la navigation sur les pages
        messages.error(request, "Vous n'avez pas les droits d'accès requis pour effectuer cette action.")
        return redirect('dashboard')
        
    return login_required(_wrapped_view)








from django.shortcuts import redirect
from django.contrib import messages
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from functools import wraps

# --- VERROU GÉRANT (Niveau Direction) ---
def gerant_only(view_func):
    """Accès : Superutilisateur + Gérant uniquement"""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if peut_voir_finance(request.user):
            return view_func(request, *args, **kwargs)
        
        # Détection si la requête vient du Switch JS (Fetch/AJAX)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'status': 'denied',
                'message': "Action refusée : Cette zone est réservée à la direction."
            }, status=403)
        
        # Redirection classique : On le maintient sur la même page si possible
        messages.error(request, "Accès refusé. Cette zone est réservée à la direction de BEL'R.")
        
        previous_page = request.META.get('HTTP_REFERER')
        if previous_page:
            return redirect(previous_page)
        return redirect('dashboard')
        
    return login_required(_wrapped_view)


# --- VERROU MANAGER (Niveau Supervision) ---
def manager_required(view_func):
    """Accès : Superutilisateur + Gérant + Manager"""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if peut_voir_gestion(request.user):
            return view_func(request, *args, **kwargs)
        
        # Détection si la requête vient du Switch JS (Fetch/AJAX)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'status': 'denied',
                'message': "Action refusée : Vous n'avez pas les droits d'accès requis."
            }, status=403)
        
        # Redirection classique : On le maintient sur la même page si possible
        messages.error(request, "Vous n'avez pas les droits d'accès requis pour effectuer cette action.")
        
        previous_page = request.META.get('HTTP_REFERER')
        if previous_page:
            return redirect(previous_page)
        return redirect('dashboard')
        
    return login_required(_wrapped_view)



# decorators.py
from django.shortcuts import redirect
from django.contrib import messages
from functools import wraps

def manager_only_strict(view_func):
    """Accès STRICT : Seul le groupe 'Manager' peut exécuter cette action. 
    Même un Gérant supérieur est bloqué."""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        # 1. Vérification stricte de l'appartenance exclusive au groupe Manager
        est_manager = request.user.groups.filter(name='Manager').exists()
        
        # 2. On laisse passer le Manager OU le Superutilisateur technique (toi pour la maintenance)
        if est_manager or request.user.is_superuser:
            return view_func(request, *args, **kwargs)
            
        # 3. Refus pour tout autre rôle (y compris Gérant)
        messages.error(request, "Alerte Sécurité : Seuls les Managers sont habilités à valider les paiements.")
        
        previous_page = request.META.get('HTTP_REFERER')
        if previous_page:
            return redirect(previous_page)
        return redirect('dashboard')
        
    return _wrapped_view


# --- VERROU EMPLOYÉ (Niveau Équipe) ---
def employe_required(view_func):
    """Accès : Tout le monde (Actif)"""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if peut_voir_espace_perso(request.user):
            return view_func(request, *args, **kwargs)
        
        # Détection si la requête vient du Switch JS (Fetch/AJAX)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'status': 'denied',
                'message': "Votre compte collaborateur n'est pas actif."
            }, status=403)
            
        # Redirection classique pour la navigation sur les pages
        messages.error(request, "Votre compte collaborateur n'est pas actif actuellement.")
        return redirect('login')
        
    return login_required(_wrapped_view)

















from django.shortcuts import redirect
from django.contrib import messages
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.utils.http import url_has_allowed_host_and_scheme
from functools import wraps

# Remplace ces imports par les chemins exacts de tes fonctions de vérification
# from .utils import peut_voir_finance, peut_voir_gestion, peut_voir_espace_perso

def valider_referer_securise(request):
    """
    Fonction utilitaire pour s'assurer que le HTTP_REFERER appartient 
    bien à l'hôte courant et utilise le protocole sécurisé attendu.
    """
    referer = request.META.get('HTTP_REFERER')
    is_safe = url_has_allowed_host_and_scheme(
        url=referer,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure()
    )
    return referer if (referer and is_safe) else None


# --- VERROU GÉRANT (Niveau Direction) ---
def gerant_only(view_func):
    """Accès : Superutilisateur + Gérant uniquement"""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if peut_voir_finance(request.user):
            return view_func(request, *args, **kwargs)
        
        # Détection si la requête vient du Switch JS (Fetch/AJAX)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'status': 'denied',
                'message': "Action refusée : Cette zone est réservée à la direction."
            }, status=403)
        
        # Redirection classique sécurisée
        messages.error(request, "Accès refusé. Cette zone est réservée à la direction de BEL'R.")
        
        previous_page = valider_referer_securise(request)
        if previous_page:
            return redirect(previous_page)
        return redirect('dashboard')
        
    return login_required(_wrapped_view)


# --- VERROU MANAGER (Niveau Supervision) ---
def manager_required(view_func):
    """Accès : Superutilisateur + Gérant + Manager"""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if peut_voir_gestion(request.user):
            return view_func(request, *args, **kwargs)
        
        # Détection si la requête vient du Switch JS (Fetch/AJAX)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'status': 'denied',
                'message': "Action refusée : Vous n'avez pas les droits d'accès requis."
            }, status=403)
        
        # Redirection classique sécurisée
        messages.error(request, "Vous n'avez pas les droits d'accès requis pour effectuer cette action.")
        
        previous_page = valider_referer_securise(request)
        if previous_page:
            return redirect(previous_page)
        return redirect('dashboard')
        
    return login_required(_wrapped_view)


# --- VERROU MANAGER STRICT ---
def manager_only_strict(view_func):
    """Accès STRICT : Seul le groupe 'Manager' ou Superutilisateur technique peut y accéder."""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        est_manager = request.user.groups.filter(name='Manager').exists()
        
        if est_manager or request.user.is_superuser:
            return view_func(request, *args, **kwargs)
            
        # Détection AJAX pour uniformiser le comportement
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'status': 'denied',
                'message': "Alerte Sécurité : Seuls les Managers sont habilités à effectuer cette action."
            }, status=403)
            
        messages.error(request, "Alerte Sécurité : Seuls les Managers sont habilités à valider les paiements.")
        
        previous_page = valider_referer_securise(request)
        if previous_page:
            return redirect(previous_page)
        return redirect('dashboard')
        
    return login_required(_wrapped_view)


# --- VERROU EMPLOYÉ (Niveau Équipe) ---
def employe_required(view_func):
    """Accès : Tout le monde (Actif)"""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if peut_voir_espace_perso(request.user):
            return view_func(request, *args, **kwargs)
        
        # Détection si la requête vient du Switch JS (Fetch/AJAX)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'status': 'denied',
                'message': "Votre compte collaborateur n'est pas actif."
            }, status=403)
            
        # Redirection classique pour la navigation sur les pages
        messages.error(request, "Votre compte collaborateur n'est pas actif actuellement.")
        return redirect('login')
        
    return login_required(_wrapped_view)