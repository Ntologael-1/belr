from django.db import models

# Create your models here.
from django.core.validators import MinValueValidator
from datetime import timedelta
from django.utils import timezone
from django.conf import settings



from django.db import models
from django.utils import timezone
import uuid



from django.db import models
from django.conf import settings
from django.utils import timezone
from django.contrib.auth import get_user_model
import uuid

User = get_user_model()

class PaiementEmploye(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='vendeur_paiements'
    )

    numero_groupe = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        db_index=True  # Déjà présent — Excellent pour lier les lignes au reçu
    )
    
    quantite = models.PositiveIntegerField(default=1)
    client_nom = models.CharField(max_length=150, null=True, blank=True)

    # INDEXÉ : Utilisé en JS ou Backend pour regrouper à la volée les éléments d'un pack
    pack_instance_id = models.CharField(max_length=50, null=True, blank=True, db_index=True)

    employe = models.ForeignKey(
        'employes.Employe',
        on_delete=models.SET_NULL,
        null=True,
        related_name='paiements'
    )

    services = models.ManyToManyField(
        'gestion.Service',
        related_name='paiements'
    )

    total_services = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0
    )

    provenance_pack = models.ForeignKey(
        'gestion.Service',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='contributions_pack'
    )

    # CRITIQUE : Le champ le plus filtré du projet pour le calcul du chiffre d'affaires quotidien/hebdomadaire
    date_paiement = models.DateTimeField(default=timezone.now, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_paiement']


class RecuClient(models.Model):
    MODE_CHOICES = [
        ('ESPECE', 'Espèces'),
        ('CARTE', 'Carte Bancaire'),
        ('MOBILE_MONEY', 'Mobile Money'),
    ]

    numero_groupe = models.UUIDField(db_index=True) # Déjà présent — Parfait
    numero_recu = models.CharField(max_length=20, unique=True) # unique=True crée déjà un index automatiquement
    nom_client = models.CharField(max_length=150, null=True, blank=True)
    total_global = models.DecimalField(max_digits=12, decimal_places=2)
    
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='recus'
    )
    
    mode_paiement = models.CharField(
        max_length=20, 
        choices=MODE_CHOICES,
    )

    employes = models.ManyToManyField(
        'employes.Employe', 
        blank=True, 
        related_name='ventes',
        help_text="Le ou les employés ayant travaillé sur ce ticket"
    )

    # INDEXÉ : Le gérant filtre souvent les tickets signalés pour validation ou suppression
    demande_suppression = models.BooleanField(
        default=False, 
        verbose_name="Signalé pour suppression",
        help_text="Coché par le manager ou l'auteur si le délai de 30 min est dépassé",
        db_index=True
    )
     
    # CRITIQUE : C'est la date de création du ticket servant aux statistiques du dashboard
    date = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return f"Reçu {self.numero_recu} - {self.nom_client or 'Anonyme'}"


class RecuSupprimeLog(models.Model):
    numero_recu = models.CharField(max_length=50)
    
    # INDEXÉ : Permet de pister l'historique d'un groupe supprimé en cas d'audit financier
    numero_groupe = models.CharField(max_length=100, db_index=True)
    
    total_global = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    supprime_par = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    
    # INDEXÉ : Pour trier rapidement l'historique d'audit du plus récent au plus ancien
    date_suppression = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return f"Reçu {self.numero_recu} supprimé le {self.date_suppression}"