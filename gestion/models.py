from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
import uuid

# Create your models here.

class Salon(models.Model):
    nom = models.CharField(max_length=200)
    adresse = models.TextField()
    telephone = models.CharField(max_length=20)
    email = models.EmailField()
    horaire_ouverture = models.CharField(max_length=100, default="9h-19h")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.nom
    
    class Meta:
        verbose_name = "Salon"
        verbose_name_plural = "Informations du Salon"






'''
class CategorieService(models.Model):
    nom = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    ordre = models.IntegerField(default=0)
    
    def __str__(self):
        return self.nom
    
    class Meta:
        ordering = ['ordre']

class Service(models.Model):
    code = models.CharField(max_length=20, unique=True)
    nom = models.CharField(max_length=200)
    categorie = models.ForeignKey(CategorieService, on_delete=models.SET_NULL, null=True)
    description = models.TextField(blank=True)
    duree = models.IntegerField(help_text="Durée en minutes")
    prix = models.DecimalField(max_digits=10, decimal_places=2)
    commission = models.IntegerField(
        default=50,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Commission en % pour le coiffeur"
    )
    actif = models.BooleanField(default=True)
    couleur = models.CharField(max_length=7, default="#007bff", help_text="Couleur hexadécimale")
    
    def __str__(self):
        return f"{self.nom} - {self.prix}€"
    
    class Meta:
        ordering = ['categorie__ordre', 'nom']


'''

class Parametre(models.Model):
    cle = models.CharField(max_length=100, unique=True)
    valeur = models.TextField()
    description = models.TextField(blank=True)
    
    def __str__(self):
        return self.cle
    






from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator

class CategorieService(models.Model):
    nom = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    ordre = models.IntegerField(default=0)
    
    def __str__(self):
        return self.nom
    
    class Meta:
        ordering = ['ordre']

class Service(models.Model):
    # Identification
    code = models.CharField(max_length=20, unique=True)
    nom = models.CharField(max_length=200)
    categorie = models.ForeignKey(CategorieService, on_delete=models.SET_NULL, null=True,blank=True)
    description = models.TextField(blank=True)
    
    # Caractéristiques techniques
    duree = models.IntegerField(help_text="Durée en minutes")
    couleur = models.CharField(max_length=7, default="#007bff", help_text="Couleur hexadécimale")
    actif = models.BooleanField(default=True)

    # Finance (Le prix sert pour le service solo OU le prix global du pack)
    prix = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        verbose_name="Prix de vente (FCFA)"
    )

    # Logique de Pack
    est_un_pack = models.BooleanField(
        default=False, 
        verbose_name="Est-ce un pack ?"
    )
    # Modifie juste cette partie dans ton Service
    services_inclus = models.ManyToManyField(
        'self', 
        symmetrical=False, 
        blank=True, 
        related_name="inclus_dans_packs",
        verbose_name="Services inclus dans ce pack"
    )

    def __str__(self):
        prefix = "[PACK] " if self.est_un_pack else ""
        return f"{prefix}{self.nom} - {self.prix} FCFA"

    class Meta:
        ordering = ['categorie__ordre', 'nom']