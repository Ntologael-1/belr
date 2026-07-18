"""
URL configuration for my_shop project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path,include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.auth import views as auth_views
from gestion import views as gestion_views
from employes import views as employes_views



urlpatterns = [
    path("admin/", admin.site.urls),

    # Authentification
    path('login/', auth_views.LoginView.as_view(template_name='auth/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('password-reset/', 
         employes_views.custom_password_reset_request, name='password_reset'), 
         
    
    # 2. Page de confirmation (Information que l'email est envoyé)
    path('password-reset/done/', 
         auth_views.PasswordResetDoneView.as_view(template_name='auth/password_reset_done.html'), 
         name='password_reset_done'),
    
    # 3. Lien secret reçu par mail (Saisie du nouveau mot de passe)
    path('password-reset/confirm/<uidb64>/<token>/', 
         auth_views.PasswordResetConfirmView.as_view(template_name='auth/password_reset_confirm.html'), 
         name='password_reset_confirm'),
    
    # 4. Page de succès final (Le mot de passe est changé, bouton de connexion)
    path('password-reset/complete/', 
         auth_views.PasswordResetCompleteView.as_view(template_name='auth/password_reset_complete.html'), 
         name='password_reset_complete'),
    
    # Applications
    path('', gestion_views.accueil, name='accueil'),
    path('dashboard', gestion_views.dashboard, name='dashboard'),
    path('gestion/', include('gestion.urls')),
    path('clients/', include('clients.urls')),
    path('rendezvous/', include('rendezvous.urls')),
    path('employes/', include('employes.urls')),
    path('inventaire/', include('inventaire.urls')),
    path('rapports/', include('rapports.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
