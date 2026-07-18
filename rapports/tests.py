from django.test import TestCase

# Create your tests here.


from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone

User = get_user_model()
# Importation de ton modèle Employe pour éviter le 404
from employes.models import Employe 

# ==============================================================================
# SUITE DE TESTS DES RAPPORTS ET DE LA BUSINESS INTELLIGENCE (BI)
# ==============================================================================
class SuiteVuesRapportsTestCase(TestCase):

    def setUp(self):
        """Configuration des profils d'accès administratifs et RH requis."""
        # Profil Manager pour visionner les rapports financiers
        self.manager = User.objects.create_user(username="directeur_salon", password="password123")
        self.manager.is_staff = True
        self.manager.is_superuser = True
        self.manager.save()

        # 1. Création de l'utilisateur pour le coiffeur
        self.user_coiffeur = User.objects.create_user(username="coiffeur_expert", password="password123")
        
        # 2. Création de l'instance d'Employe requise par la vue rapport_coiffeur_detail
        self.employe_test = Employe.objects.create(
            user=self.user_coiffeur,
            matricule="MAT-BI-99",
            date_embauche=timezone.now().date(),
            telephone="+237600000000",
            actif=True
        )

    def test_vue_rapport_global_accessible(self):
        """Vérifie l'affichage du bilan d'activité et flux financier global."""
        self.client.login(username="directeur_salon", password="password123")
        response = self.client.get(reverse('rapports:rapport_global'))
        self.assertEqual(response.status_code, 200)

    def test_vue_dashboard_bi_couts_accessible(self):
        """Vérifie le chargement des indicateurs BI de charges et rentabilité."""
        self.client.login(username="directeur_salon", password="password123")
        response = self.client.get(reverse('rapports:dashboard_bi'))
        self.assertEqual(response.status_code, 200)

    def test_vue_rapport_coiffeur_detail_accessible(self):
        """Vérifie la fiche de performance avec une vraie instance d'employé."""
        self.client.login(username="directeur_salon", password="password123")
        # On passe ici la clé primaire (pk) de l'employé créé pour valider la contrainte
        response = self.client.get(
            reverse('rapports:rapport_coiffeur_detail', kwargs={'employe_id': self.employe_test.pk})
        )
        self.assertEqual(response.status_code, 200)

    def test_vue_rapport_annuel_accessible(self):
        """Vérifie la consolidation et comparaisons d'activité Year-over-Year."""
        self.client.login(username="directeur_salon", password="password123")
        response = self.client.get(reverse('rapports:rapport_annuel'))
        self.assertEqual(response.status_code, 200)

    def test_fonctionnalite_executer_consolidation_belr(self):
        """Vérifie le déclenchement de la consolidation des calculs analytiques."""
        self.client.login(username="directeur_salon", password="password123")
        
        url = reverse('rapports:rapport_annuel')
        response = self.client.post(url, {'action': 'consolider_belr'})
        
        self.assertIn(response.status_code, [200, 302])
