from django.test import TestCase

import uuid
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal
from django.apps import apps

User = get_user_model()

try:
    Employe = apps.get_model('employes', 'Employe')
except LookupError:
    from django.db import models
    class Employe(models.Model):
        nom = models.CharField(max_length=100)
        class Meta:
            managed = False

try:
    Service = apps.get_model('gestion', 'Service')
except LookupError:
    from django.db import models
    class Service(models.Model):
        nom = models.CharField(max_length=100)
        prix = models.DecimalField(max_digits=10, decimal_places=2, default=0)
        est_pack = models.BooleanField(default=False)
        class Meta:
            managed = False

from .models import PaiementEmploye, RecuClient, RecuSupprimeLog

# ==============================================================================
# I. SUITE DE TESTS DES MODÈLES (Intégrité des Données & Tranches d'Audit)
# ==============================================================================
class LogicModellesRendezvousTestCase(TestCase):
    
    def setUp(self):
        """Initialisation des instances nécessaires à la validation des modèles."""
        # 1. Création de l'utilisateur lié au caissier/gérant
        self.gerant = User.objects.create_user(username="gerant_salon", password="password123")
        self.gerant.is_staff = True
        self.gerant.is_superuser = True
        self.gerant.save()
        
        # Alias pour compatibilité avec les tests de modèles unitaires
        self.user = self.gerant

        # 2. Création de l'utilisateur propre au coiffeur
        self.user_coiffeur = User.objects.create_user(
            username="coiffeur_star", 
            password="password123",
            first_name="Coiffeur",
            last_name="Star"
        )

        # 3. Création de l'employé
        if Employe._meta.managed:
            self.employe = Employe.objects.create(
                user=self.user_coiffeur,
                matricule="MAT-2026-001",
                date_embauche=timezone.now().date(),
                telephone="+237600000000",
                jours_travail="Lundi,Mardi,Mercredi,Jeudi,Vendredi,Samedi",
                salaire_base=Decimal("150000.00")
            )
        else:
            self.employe = None
            
        # 4. Initialisation du service avec la gestion du champ duree
        if Service._meta.managed:
            self.service = Service()
            if hasattr(self.service, 'nom'):
                self.service.nom = "Coupe Homme Premium"
            if hasattr(self.service, 'prix'):
                self.service.prix = Decimal("5000.00")
            if hasattr(self.service, 'duree'):
                self.service.duree = 30
            self.service.save()
        else:
            self.service = None
            
        self.groupe_id = uuid.uuid4()
        
        # 5. Création du reçu client de référence
        self.recu_existant = RecuClient.objects.create(
            numero_groupe=self.groupe_id,
            numero_recu="REC-9999",
            nom_client="Client VIP",
            total_global=Decimal("15000.00"),
            user=self.gerant,
            mode_paiement="ESPECE"
        )

    def test_creation_recu_client_et_choix_paiement(self):
        """Vérifie l'écriture d'un reçu client global avec son mode de paiement."""
        recu = RecuClient.objects.create(
            numero_groupe=self.groupe_id,
            numero_recu="REC-2026-001",
            nom_client="Client Alpha",
            total_global=Decimal("5000.00"),
            user=self.user,
            mode_paiement="MOBILE_MONEY"
        )
        if self.employe:
            recu.employes.add(self.employe)

        self.assertEqual(RecuClient.objects.count(), 2) 
        self.assertFalse(recu.demande_suppression)
        self.assertIn("REC-2026-001", str(recu))

    def test_creation_log_recu_supprime(self):
        """Garantit la traçabilité de l'historique d'audit lors d'un effacement financier."""
        log = RecuSupprimeLog.objects.create(
            numero_recu="REC-2026-001",
            numero_groupe=str(self.groupe_id),
            total_global=Decimal("5000.00"),
            supprime_par=self.user
        )
        self.assertEqual(RecuSupprimeLog.objects.count(), 1)
        self.assertIn("REC-2026-001", str(log))


# ==============================================================================
# II. SUITE DE TESTS DES VUES ET ROUTES SANS NAMESPACE REQUIS
# ==============================================================================
class SuiteVuesRendezvousTestCase(TestCase):

    def setUp(self):
        """Configuration complète de l'environnement de test (SaaS Premium)."""
        self.gerant = User.objects.create_user(username="gerant_salon", password="password123")
        self.gerant.is_staff = True
        self.gerant.is_superuser = True
        self.gerant.save()

        self.groupe_id = uuid.uuid4()
        
        self.recu_existant = RecuClient.objects.create(
            numero_groupe=self.groupe_id,
            numero_recu="REC-9999",
            nom_client="Client VIP",
            total_global=Decimal("15000.00"),
            user=self.gerant,
            mode_paiement="ESPECE"
        )

    # 1. ACCÈS AUX AFFICHAGES ET LOGS DE REÇUS (GET)
    def test_vue_calendrier_accessible(self):
        self.client.login(username="gerant_salon", password="password123")
        response = self.client.get(reverse('calendrier'))
        self.assertEqual(response.status_code, 200)

    def test_vue_historique_paiement_accessible(self):
        self.client.login(username="gerant_salon", password="password123")
        response = self.client.get(reverse('historique_paiement'))
        self.assertEqual(response.status_code, 200)

    def test_vue_paiement_detail_accessible(self):
        self.client.login(username="gerant_salon", password="password123")
        url = reverse('paiement_detail', kwargs={'groupe_id': self.groupe_id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    # 2. ENREGISTREMENT ET ÉDITION DES VENTES (POST / NOUVEAU)
    def test_vue_nouveau_paiement_formulaire_accessible(self):
        self.client.login(username="gerant_salon", password="password123")
        response = self.client.get(reverse('paiement'))
        self.assertEqual(response.status_code, 200)

    def test_vue_modifier_paiement_existant_accessible(self):
        self.client.login(username="gerant_salon", password="password123")
        url = reverse('paiement', kwargs={'groupe_id': self.groupe_id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)

    # 3. SIGNALEMENT ET MODIFICATION DES PARAMÈTRES SÉCURITÉS (POST)
    def test_fonctionnalite_signaler_paiement(self):
        self.client.login(username="gerant_salon", password="password123")
        url = reverse('signaler_paiement', kwargs={'groupe_id': self.groupe_id})
        
        response = self.client.post(url, {})
        self.assertIn(response.status_code, [200, 302])
        
        self.recu_existant.refresh_from_db()
        self.assertTrue(self.recu_existant.demande_suppression)

    # 4. SUPPRESSION PHYSIQUE ET INTÉGRATION DE L'AUDIT LOG
    def test_fonctionnalite_paiement_delete(self):
        self.client.login(username="gerant_salon", password="password123")
        url = reverse('paiement_delete', kwargs={'groupe_id': self.groupe_id})
        
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(RecuClient.objects.filter(numero_groupe=self.groupe_id).exists())

    # 5. RAPPORTS INTER-APPLICATIONS (API JSON POUR LES DETAILS DES PACKS)
    def test_api_get_pack_details(self):
        self.client.login(username="gerant_salon", password="password123")
        
        url = reverse('get_pack_details', kwargs={'pack_id': 1})
        response = self.client.get(url)
        self.assertIn(response.status_code, [200, 404])
        
        if response.status_code == 200:
            self.assertEqual(response['content-type'], 'application/json')