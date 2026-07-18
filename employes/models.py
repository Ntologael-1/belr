from django.db import models

# Create your models here.
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from datetime import date



from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from datetime import date

class Employe(models.Model):
    TYPE_CONTRAT_CHOICES = [
        ('CDI', 'CDI'),
        ('CDD', 'CDD'),
        ('INTERIM', 'Intérim'),
        ('STAGIAIRE', 'Stagiaire'),
        ('INDEPENDANT', 'Indépendant'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='employe')
    
    # Informations professionnelles
    matricule = models.CharField(max_length=20, unique=True)
    specialite = models.CharField(max_length=200, blank=True)
    type_contrat = models.CharField(max_length=20, choices=TYPE_CONTRAT_CHOICES, default='CDI')
    date_embauche = models.DateField()
    date_fin_contrat = models.DateField(null=True, blank=True)
    
    # Rémunération Fixe (Nouveau Système)
    salaire_base = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text="Salaire fixe en FCFA")
    
    # Paramétrage des Paliers de Bonus
    palier_1_ca = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    palier_1_percent = models.IntegerField(default=0, help_text="% si CA > Palier 1")
    
    palier_2_ca = models.DecimalField(max_digits=12, decimal_places=2, default=500000)
    palier_2_percent = models.IntegerField(default=0, help_text="% si CA > Palier 2")

    # Disponibilités
    jours_travail = models.JSONField(default=list, blank=True)
    heure_debut = models.TimeField(default='09:00')
    heure_fin = models.TimeField(default='19:00')
    
    # Statut & Design
    actif = models.BooleanField(default=True)
    photo = models.ImageField(upload_to='employes/', blank=True, null=True)
    couleur_calendrier = models.CharField(max_length=7, default='#007bff')
    
    # Contact
    telephone = models.CharField(max_length=20)
    telephone_urgence = models.CharField(max_length=20, blank=True)
    contact_urgence = models.CharField(max_length=100, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['user__last_name', 'user__first_name']
        verbose_name = "Employé"
        verbose_name_plural = "Employés"

    def __str__(self):
        return self.nom_complet

    # --- Properties ---
    @property
    def nom_complet(self):
        if self.user.first_name or self.user.last_name:
            return f"{self.user.first_name} {self.user.last_name}".strip()
        return self.user.username

    @property
    def anciennete(self):
        if self.date_embauche:
            delta = date.today() - self.date_embauche
            return delta.days // 365
        return 0


    @property
    def est_disponible(self):
        """Vérifie si l'employé travaille aujourd'hui (nom du jour en français)"""
        from datetime import date
        # Traduction simple pour correspondre à ta chaîne "Lundi,Mardi..."
        jours_traduction = {
            'Monday': 'Lundi', 'Tuesday': 'Mardi', 'Wednesday': 'Mercredi',
            'Thursday': 'Jeudi', 'Friday': 'Vendredi', 'Saturday': 'Samedi', 'Sunday': 'Dimanche'
        }
        jour_actuel = jours_traduction[date.today().strftime('%A')]
        return self.actif and jour_actuel in self.jours_travail_list






    @property
    def jours_travail_list(self):
        if not self.jours_travail:
            return []
        return [j.strip() for j in self.jours_travail.split(',')]

    # --- Logique métier ---
    def calculer_bonus(self, ca_mensuel, p1_ca=None, p1_pct=None, p2_ca=None, p2_pct=None):
        """Calcule le bonus selon les paliers fournis (historique) ou actifs par défaut"""
        ca = float(ca_mensuel)
        
        # Sélection des paliers : historique si fourni, sinon valeur actuelle de l'employé
        limite_p2 = float(p2_ca) if p2_ca is not None else float(self.palier_2_ca)
        pct_p2    = float(p2_pct) if p2_pct is not None else float(self.palier_2_percent)
        
        limite_p1 = float(p1_ca) if p1_ca is not None else float(self.palier_1_ca)
        pct_p1    = float(p1_pct) if p1_pct is not None else float(self.palier_1_percent)

        if ca >= limite_p2:
            return ca * (pct_p2 / 100)
        elif ca >= limite_p1:
            return ca * (pct_p1 / 100)
        return 0