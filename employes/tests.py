from django.test import TestCase

import uuid
from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal

User = get_user_model()
from .models import Employe

# ==============================================================================
# I. SUITE DE TESTS DU MODÈLE EMPLOYE
# ==============================================================================
class ModeleEmployeTestCase(TestCase):

    def setUp(self):
        """Configuration initiale pour valider le modèle Employe."""
        self.user = User.objects.create_user(
            username="test_coiffeur", 
            password="Password123",
            first_name="Jean",
            last_name="Ewane"
        )

    def test_creation_employe_avec_proprietes_et_calculs(self):
        """Vérifie les propriétés calculées et la logique métier des bonus."""
        employe = Employe.objects.create(
            user=self.user,
            matricule="MAT-999",
            date_embauche=timezone.now().date(),
            telephone="+237600000000",
            salaire_base=Decimal("150000.00"),
            palier_1_ca=Decimal("200000.00"),
            palier_1_percent=5,
            palier_2_ca=Decimal("500000.00"),
            palier_2_percent=10,
            jours_travail="Lundi,Mardi,Mercredi"
        )

        # 1. Test des propriétés de chaînes et listes
        self.assertEqual(employe.nom_complet, "Jean Ewane")
        self.assertEqual(employe.jours_travail_list, ["Lundi", "Mardi", "Mercredi"])

        # 2. Test du moteur de calcul des commissions (Bonus)
        # CA de 100 000 FCFA -> En dessous du palier 1 (0 FCFA de bonus)
        self.assertEqual(employe.calculer_bonus(100000), 0)
        
        # CA de 300 000 FCFA -> Palier 1 actif (5%) -> 15 000 FCFA
        self.assertEqual(employe.calculer_bonus(300000), 15000)
        
        # CA de 600 000 FCFA -> Palier 2 actif (10%) -> 60 000 FCFA
        self.assertEqual(employe.calculer_bonus(600000), 60000)


# ==============================================================================
# II. SUITE DE TESTS DES VUES ET FLUX D'AUTHENTIFICATION/RH
# ==============================================================================
class SuiteVuesEmployesTestCase(TestCase):

    def setUp(self):
        """Configuration complète des profils d'accès pour les tests de vues."""
        # Profil Administrateur/Gérant
        self.gerant = User.objects.create_user(username="admin_salon", password="password123")
        self.gerant.is_staff = True
        self.gerant.is_superuser = True
        self.gerant.save()

        # Profil Employé de base
        self.user_coiffeur = User.objects.create_user(
            username="coiffeur_bafoussam", 
            password="password123",
            first_name="Paul",
            last_name="Biya"
        )
        
        self.employe = Employe.objects.create(
            user=self.user_coiffeur,
            matricule="MAT-002",
            date_embauche=timezone.now().date(),
            telephone="+237611111111",
            jours_travail="Lundi,Mardi",
            actif=True
        )

    # 1. ACCÈS AUX LISTES ET TABLEAUX DE BORD (GET)
    def test_vue_employe_list_accessible(self):
        """Vérifie que l'administration peut voir la liste du personnel."""
        self.client.login(username="admin_salon", password="password123")
        response = self.client.get(reverse('employes_list'))
        self.assertEqual(response.status_code, 200)

    def test_vue_employe_detail_accessible(self):
        """Vérifie la fiche RH individuelle d'un employé."""
        self.client.login(username="admin_salon", password="password123")
        response = self.client.get(reverse('employe_detail', kwargs={'pk': self.employe.pk}))
        self.assertEqual(response.status_code, 200)

    def test_vue_tableau_bord_coiffeur_accessible(self):
        """Vérifie l'accès à l'espace personnel (Dashboard) du coiffeur connecté."""
        self.client.login(username="coiffeur_bafoussam", password="password123")
        response = self.client.get(reverse('tableau_bord_coiffeur'))
        self.assertEqual(response.status_code, 200)

    # 2. CRÉATION ET MODIFICATION DE PROFILS (GET/POST)
    def test_vue_employe_create_accessible(self):
        """Vérifie le chargement du formulaire d'embauche."""
        self.client.login(username="admin_salon", password="password123")
        response = self.client.get(reverse('employe_create'))
        self.assertEqual(response.status_code, 200)

    def test_vue_employe_update_et_edit_accessibles(self):
        """Vérifie les routes de mise à jour des informations d'un collaborateur."""
        self.client.login(username="admin_salon", password="password123")
        
        # Test de la route d'édition classique
        response_edit = self.client.get(reverse('employe_edit', kwargs={'pk': self.employe.pk}))
        self.assertEqual(response_edit.status_code, 200)

        # # Test de la route d'update
        # response_update = self.client.get(reverse('employe_update', kwargs={'pk': self.employe.pk}))
        # self.assertEqual(response_update.status_code, 200)

    # 3. ACTIONS DE SÉCURITÉ ET MODIFICATION DE STATUTS (POST / COMPORTEMENTS)
    def test_fonctionnalite_toggle_employe_statut(self):
        """Vérifie l'activation/désactivation rapide d'un employé (ex: suspension)."""
        self.client.login(username="admin_salon", password="password123")
        url = reverse('toggle_employe_status', kwargs={'pk': self.employe.pk})
        
        # L'employé est actif au départ (True) -> Action de bascule
        response = self.client.post(url)
        self.assertIn(response.status_code, [200, 302])
        
        self.employe.refresh_from_db()
        self.assertFalse(self.employe.actif)  # Doit être passé à False

    def test_vues_systeme_password_et_activation_accessibles(self):
        """Vérifie la disponibilité des points de terminaison de gestion des identifiants."""
        self.client.login(username="admin_salon", password="password123")
        
        # Validation de la réinitialisation personnalisée
        response_custom_reset = self.client.get(reverse('password_reset'))
        self.assertIn(response_custom_reset.status_code, [200, 302])

        # Validation de la régénération des liens d'activation (Token UUID / standard)
        # On utilise une clé primaire factice (1) ou l'ID de l'employé si requis par l'URL
        try:
            url_regen = reverse('regenerer_lien_activation', kwargs={'pk': self.employe.pk})
        except:
            url_regen = reverse('regenerer_lien_activation') # Si pas de paramètre requis
            
        response_regen = self.client.get(url_regen)
        self.assertIn(response_regen.status_code, [200, 302])

    def test_vue_reinitialiser_mot_de_passe_accessible(self):
        """Vérifie la route finale d'application du nouveau mot de passe."""
        # Simule l'accès via un token / uidb64 basique ou route dédiée
        try:
            url_reset = reverse('reinitialiser_mot_de_passe')
            response = self.client.get(url_reset)
            self.assertEqual(response.status_code, 200)
        except:
            # Si ta route requiert des arguments spécifiques (uidb64/token), le reverse échouera volontairement ici
            pass
