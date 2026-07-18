from django.contrib import admin

# Register your models here.
from django.contrib import admin
from django.utils.html import format_html
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import Employe


# ==========================================
#  INLINE : Employé dans User
# ==========================================
'''
class EmployeInline(admin.StackedInline):
    model = Employe
    can_delete = False
    verbose_name_plural = "Employé"


class UserAdmin(BaseUserAdmin):
    inlines = (EmployeInline,)


admin.site.unregister(User)
admin.site.register(User, UserAdmin)


# ==========================================
#  ADMIN EMPLOYÉ
# ==========================================

@admin.register(Employe)
class EmployeAdmin(admin.ModelAdmin):

    list_display = (
        "nom",
        "matricule",
        "specialite",
        "type_contrat",
        "taux_commission",
        "actif",
        "anciennete_affichee",
        "disponible",
        "photo_preview",
    )

    list_filter = (
        "type_contrat",
        "actif",
        "date_embauche",
    )

    search_fields = (
        "user__first_name",
        "user__last_name",
        "matricule",
        "telephone",
        "specialite",
    )

    ordering = ("user__last_name",)

    readonly_fields = (
        "created_at",
        "updated_at",
        "anciennete",
        "photo_preview",
    )

    fieldsets = (
        ("Compte", {
            "fields": ("user", "matricule", "actif", "photo", "photo_preview")
        }),
        ("Professionnel", {
            "fields": ("specialite", "type_contrat", "date_embauche", "date_fin_contrat")
        }),
        ("Rémunération", {
            "fields": ("taux_horaire", "taux_commission")
        }),
        ("Disponibilités", {
            "fields": ("jours_travail", "heure_debut", "heure_fin", "couleur_calendrier")
        }),
        ("Contact", {
            "fields": ("telephone", "telephone_urgence", "contact_urgence")
        }),
        ("Système", {
            "fields": ("created_at", "updated_at", "anciennete")
        }),
    )


    # ============================
    # Affichages personnalisés
    # ============================

    def nom(self, obj):
        return obj.nom_complet
    nom.short_description = "Nom"

    def anciennete_affichee(self, obj):
        return f"{obj.anciennete} ans"
    anciennete_affichee.short_description = "Ancienneté"

    def disponible(self, obj):
        if obj.est_disponible:
            return format_html('<b style="color:green">✔ Disponible</b>')
        return format_html('<b style="color:red">✖ Indisponible</b>')
    disponible.short_description = "Aujourd’hui"

    def photo_preview(self, obj):
        if obj.photo:
            return format_html('<img src="{}" width="50" style="border-radius:50%"/>', obj.photo.url)
        return "—"
    photo_preview.short_description = "Photo"

    
'''




from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from django.utils.html import format_html
from .models import Employe

# ==========================================
#  INLINE : Employé dans User
# ==========================================

class EmployeInline(admin.StackedInline):
    model = Employe
    can_delete = False
    verbose_name_plural = "Profil Employé BEL'R"
    # Optionnel : on peut restreindre les champs affichés dans l'inline User
    fields = ('matricule', 'specialite', 'actif', 'salaire_base')

class UserAdmin(BaseUserAdmin):
    inlines = (EmployeInline,)

admin.site.unregister(User)
admin.site.register(User, UserAdmin)


# ==========================================
#  ADMIN EMPLOYÉ
# ==========================================

@admin.register(Employe)
class EmployeAdmin(admin.ModelAdmin):

    # Mise à jour du list_display avec les nouveaux champs financiers
    list_display = (
        "photo_preview",
        "nom_affichage",
        "matricule",
        "type_contrat",
        "salaire_base_formatte",
        "actif",
        "disponible",
    )

    list_filter = (
        "type_contrat",
        "actif",
        "date_embauche",
    )

    search_fields = (
        "user__first_name",
        "user__last_name",
        "matricule",
        "telephone",
        "specialite",
    )

    ordering = ("user__last_name",)

    readonly_fields = (
        "created_at",
        "updated_at",
        "anciennete_affichee",
        "photo_preview",
    )

    # Réorganisation des Fieldsets pour inclure les Paliers
    fieldsets = (
        ("Compte & Identité", {
            "fields": ("user", "matricule", "actif", "photo", "photo_preview")
        }),
        ("Contrat", {
            "fields": ("specialite", "type_contrat", "date_embauche", "date_fin_contrat")
        }),
        ("Rémunération & Performance (Paliers)", {
            "description": "Configuration du salaire fixe et des bonus basés sur le CA mensuel.",
            "fields": (
                "salaire_base", 
                ("palier_1_ca", "palier_1_percent"), 
                ("palier_2_ca", "palier_2_percent")
            )
        }),
        ("Disponibilités", {
            "fields": ("jours_travail", "heure_debut", "heure_fin", "couleur_calendrier")
        }),
        ("Contact Urgence", {
            "fields": ("telephone", "telephone_urgence", "contact_urgence")
        }),
        ("Informations Système", {
            "classes": ("collapse",), # Section repliée par défaut
            "fields": ("created_at", "updated_at", "anciennete_affichee")
        }),
    )

    # ============================
    # Méthodes d'affichage
    # ============================

    def nom_affichage(self, obj):
        return obj.nom_complet
    nom_affichage.short_description = "Nom Complet"

    def salaire_base_formatte(self, obj):
        return format_html('<b>{} FCFA</b>', obj.salaire_base)
    salaire_base_formatte.short_description = "Salaire Fixe"

    def anciennete_affichee(self, obj):
        return f"{obj.anciennete} ans"
    anciennete_affichee.short_description = "Ancienneté"

    def disponible(self, obj):
        if obj.est_disponible:
            return format_html('<span style="color:green">● Disponible</span>')
        return format_html('<span style="color:red">○ Indisponible</span>')
    disponible.short_description = "Statut (Aujourd'hui)"

    def photo_preview(self, obj):
        if obj.photo:
            return format_html('<img src="{}" width="45" height="45" style="border-radius:50%; object-fit:cover; border:1px solid #ddd;"/>', obj.photo.url)
        return format_html('<div style="width:45px; height:45px; border-radius:50%; background:#eee; display:flex; align-items:center; justify-content:center; color:#999;">?</div>')
    photo_preview.short_description = "Photo"