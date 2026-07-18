from django.test import TestCase

# Create your tests here.

from django.test import TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from decimal import Decimal
from .models import Service

User = get_user_model()

# ==============================================================================
# I. SUITE DE TESTS DU MODÈLE SERVICE
# ==============================================================================
class ModeleServiceTestCase(TestCase):

    def test_creation_service_avec_champs_obligatoires(self):
        """Vérifie la bonne persistance d'une prestation en base de données."""
        service = Service.objects.create(
            nom="Coiffure Homme Premium",
            prix=Decimal("5000.00"),
            duree=30,
        )
        self.assertEqual(Service.objects.count(), 1)
        self.assertEqual(service.nom, "Coiffure Homme Premium")


# ==============================================================================
# II. SUITE DE TESTS DES VUES ALIGNÉE SUR TES URLS
# ==============================================================================
class SuiteVuesGestionTestCase(TestCase):

    def setUp(self):
        """Configuration de l'environnement avec un compte Manager et un service."""
        self.manager = User.objects.create_user(username="manager_salon", password="password123")
        self.manager.is_staff = True
        self.manager.is_superuser = True
        self.manager.save()

        self.service_test = Service.objects.create(
            nom="Soin Visage Hydratant",
            prix=Decimal("12000.00"),
            duree=45,
        )

    def test_vue_services_list_accessible(self):
        """Vérifie l'affichage du catalogue avec ton nom exact 'services_list'."""
        self.client.login(username="manager_salon", password="password123")
        response = self.client.get(reverse('services_list')) # Ajusté avec le 's'
        self.assertEqual(response.status_code, 200)

    def test_vue_service_detail_accessible(self):
        """Vérifie le rendu de la vue détail avec le paramètre service_id."""
        self.client.login(username="manager_salon", password="password123")
        response = self.client.get(reverse('service_detail', kwargs={'service_id': self.service_test.pk}))
        self.assertEqual(response.status_code, 200)

    def test_vue_service_create_accessible(self):
        """Vérifie le chargement de l'interface d'ajout."""
        self.client.login(username="manager_salon", password="password123")
        response = self.client.get(reverse('service_create'))
        self.assertEqual(response.status_code, 200)

    def test_vue_service_edit_accessible(self):
        """Vérifie l'accès au formulaire de modification."""
        self.client.login(username="manager_salon", password="password123")
        response = self.client.get(reverse('service_edit', kwargs={'pk': self.service_test.pk}))
        self.assertEqual(response.status_code, 200)

    def test_fonctionnalite_service_delete(self):
        """Garantit la suppression d'une prestation."""
        self.client.login(username="manager_salon", password="password123")
        url = reverse('service_delete', kwargs={'pk': self.service_test.pk})
        response = self.client.post(url)
        self.assertIn(response.status_code, [200, 302])
        self.assertFalse(Service.objects.filter(pk=self.service_test.pk).exists())