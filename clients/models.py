from django.db import models
from django.core.validators import RegexValidator
import uuid
# Create your models here.


def generer_code_client():
    # S'exécute à chaque fois qu'un client est créé en base de données
    return uuid.uuid4().hex[:8].upper()

class Client(models.Model):
    GENRE_CHOICES = [
        ('M', 'Masculin'),
        ('F', 'Féminin'),
        ('A', 'Autre'),
    ]
    
    code = models.CharField(max_length=20, unique=True, default=generer_code_client)
    nom = models.CharField(max_length=100)
    prenom = models.CharField(max_length=100)
    genre = models.CharField(max_length=1, choices=GENRE_CHOICES, blank=True)
    telephone = models.CharField(
        max_length=20,
        validators=[RegexValidator(r'^[0-9\+ ]+$', 'Numéro de téléphone invalide')]
    )
    email = models.EmailField(blank=True)
    date_naissance = models.DateField(null=True, blank=True)
    adresse = models.TextField(blank=True)
    ville = models.CharField(max_length=100, blank=True)
    code_postal = models.CharField(max_length=10, blank=True)
    
    # Informations salon
    date_premiere_visite = models.DateField(auto_now_add=True)
    date_derniere_visite = models.DateField(null=True, blank=True)
    allergies = models.TextField(blank=True, help_text="Allergies ou contre-indications")
    preferences = models.TextField(blank=True, help_text="Préférences stylistiques")
    notes = models.TextField(blank=True)
    
    # Fidélité
    points_fidelite = models.IntegerField(default=0)
    parrain = models.ForeignKey('self', on_delete=models.SET_NULL, null=True, blank=True, related_name='filleuls')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['nom', 'prenom']
        verbose_name = "Client"
        verbose_name_plural = "Clients"
    
    def __str__(self):
        return f"{self.prenom} {self.nom}"
    
    def save(self, *args, **kwargs):
        if not self.code:
            self.code = uuid.uuid4().hex[:8].upper()
        super().save(*args, **kwargs)
    
    @property
    def nom_complet(self):
        return f"{self.prenom} {self.nom}"
    
    @property
    def age(self):
        if self.date_naissance:
            from datetime import date
            today = date.today()
            return today.year - self.date_naissance.year - (
                (today.month, today.day) < (self.date_naissance.month, self.date_naissance.day)
            )
        return None

class HistoriqueVisite(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='historique')
    date_visite = models.DateTimeField()
    employe = models.ForeignKey('employes.Employe', on_delete=models.SET_NULL, null=True)
    service = models.ForeignKey('gestion.Service', on_delete=models.SET_NULL, null=True)
    montant = models.DecimalField(max_digits=10, decimal_places=2)
    satisfaction = models.IntegerField(null=True, blank=True, choices=[(i, str(i)) for i in range(1, 6)])
    commentaire = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-date_visite']
    
    def __str__(self):
        return f"{self.client} - {self.date_visite.date()}"
