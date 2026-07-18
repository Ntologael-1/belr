from django.test import TestCase

from django.test import TestCase
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from decimal import Decimal
from .models import Produit, MouvementStock, StockMensuelSnapshot

class LogiqueStockBelRTestCase(TestCase):

    def setUp(self):
        """Configuration initiale d'un environnement de test propre."""
        self.user = User.objects.create_user(username="manager_test", password="password123")
        
        # Création d'un produit initial avec 10 unités à 1 000 FCFA l'unité
        self.produit = Produit.objects.create(
            nom="Shampooing Traitant BEL'R",
            code="SHAMP-BELR",
            quantite_stock=Decimal('10.00'),
            quantite_stock_theorique=Decimal('10.00'),
            prix_achat_moyen=Decimal('1000.00'),
            dernier_prix_achat=Decimal('1000.00'),
            valeur_stock_totale=Decimal('10000.00'),
            actif=True
        )

    def test_1_creation_entree_et_calcul_pamp(self):
        """Valide qu'une nouvelle entrée incrémente les stocks et recalcule le PAMP."""
        # Achat de 5 nouvelles unités à 1 300 FCFA l'unité
        mouvement = MouvementStock.objects.create(
            produit=self.produit,
            type_mouvement='ENTREE',
            quantite=Decimal('5.00'),
            prix_achat_unitaire=Decimal('1300.00'),
            is_automatique=False,
            created_by=self.user
        )

        self.produit.refresh_from_db()

        # Stock attendu : 10 + 5 = 15
        self.assertEqual(self.produit.quantite_stock, Decimal('15.00'))
        self.assertEqual(self.produit.quantite_stock_theorique, Decimal('15.00'))

        # PAMP attendu : ((10 * 1000) + (5 * 1300)) / 15 = 1100.00 FCFA
        self.assertEqual(self.produit.prix_achat_moyen, Decimal('1100.00'))
        self.assertEqual(mouvement.pamp_historique, Decimal('1100.00'))

    def test_2_sortie_automatique_versus_manuelle(self):
        """Vérifie l'isolation entre la sortie théorique (caisse) et la sortie réelle (inventaire)."""
        # 1. Sortie Automatique (Vente en Caisse) : affecte uniquement le théorique
        MouvementStock.objects.create(
            produit=self.produit,
            type_mouvement='SORTIE',
            quantite=Decimal('2.00'),
            is_automatique=True,
            created_by=self.user
        )
        self.produit.refresh_from_db()
        self.assertEqual(self.produit.quantite_stock_theorique, Decimal('8.00'))
        self.assertEqual(self.produit.quantite_stock, Decimal('10.00')) # Le stock réel reste figé

        # 2. Sortie Manuelle (Contrôle Inventaire) : La quantité saisie devient le nouveau stock réel
        MouvementStock.objects.create(
            produit=self.produit,
            type_mouvement='SORTIE',
            quantite=Decimal('7.00'), # Le manager constate qu'il ne reste que 7 unités en rayon
            is_automatique=False,
            created_by=self.user
        )
        self.produit.refresh_from_db()
        self.assertEqual(self.produit.quantite_stock, Decimal('7.00'))

    def test_3_garde_fou_securite_clean(self):
        """Vérifie que la méthode clean bloque un reste déclaré aberrant (supérieur au stock dispo)."""
        mouvement_invalide = MouvementStock(
            produit=self.produit,
            type_mouvement='SORTIE',
            quantite=Decimal('15.00'), # 15 déclaré alors qu'il n'y a que 10 en stock
            is_automatique=False,
            created_by=self.user
        )
        
        with self.assertRaises(ValidationError):
            mouvement_invalide.clean()

    def test_4_restoration_relative_a_la_suppression(self):
        """Scénario sur le passé : Vérifie que supprimer un ancien mouvement recalcule et restaure le passé sans corrompre le présent."""
        # Étape A : On fait une entrée (Achat de 10 unités à 2000 FCFA) -> Stock passe à 20, PAMP à 1500 FCFA
        achat = MouvementStock.objects.create(
            produit=self.produit,
            type_mouvement='ENTREE',
            quantite=Decimal('10.00'),
            prix_achat_unitaire=Decimal('2000.00'),
            is_automatique=False,
            created_by=self.user
        )

        # Étape B : On fait une sortie automatique de 3 unités (Stock théorique passe à 17)
        vente = MouvementStock.objects.create(
            produit=self.produit,
            type_mouvement='SORTIE',
            quantite=Decimal('3.00'),
            is_automatique=True,
            created_by=self.user
        )

        self.produit.refresh_from_db()
        self.assertEqual(self.produit.quantite_stock_theorique, Decimal('17.00'))

        # Étape C : Suppression de l'achat passé. 
        # La logique de restauration doit retirer les 10 unités de l'achat annulé et restaurer le PAMP à sa valeur précédente (1000 FCFA).
        achat.delete()
        
        self.produit.refresh_from_db()
        # Stock théorique attendu après restauration relative : 17 - 10 = 7
        self.assertEqual(self.produit.quantite_stock_theorique, Decimal('7.00'))
        # Le PAMP doit être revenu à sa valeur initiale avant l'achat
        self.assertEqual(self.produit.prix_achat_moyen, Decimal('1000.00'))

    def test_5_blocage_suppression_chronologique(self):
        """Vérifie qu'on ne peut pas supprimer un inventaire (SORTIE manuelle) si un plus récent existe."""
        inv_ancien = MouvementStock.objects.create(
            produit=self.produit,
            type_mouvement='SORTIE',
            quantite=Decimal('8.00'),
            is_automatique=False,
            created_by=self.user
        )
        
        # On simule un décalage de temps pour le second mouvement
        inv_recent = MouvementStock.objects.create(
            produit=self.produit,
            type_mouvement='SORTIE',
            quantite=Decimal('6.00'),
            is_automatique=False,
            created_by=self.user
        )

        # Tenter de supprimer l'ancien doit lever une ValidationError
        with self.assertRaises(ValidationError):
            inv_ancien.delete()

    def test_6_integration_snapshot_mensuel_bi(self):
        """Vérifie que les snapshots de fin de mois capturent fidèlement les états de stock successifs."""
        maintenant = timezone.now()
        
        # Déclenchement d'une action de stock
        MouvementStock.objects.create(
            produit=self.produit,
            type_mouvement='ENTREE',
            quantite=Decimal('2.00'),
            prix_achat_unitaire=Decimal('1000.00'),
            is_automatique=False,
            created_by=self.user
        )

        # Extraction du snapshot généré par le signal interne
        snapshot = StockMensuelSnapshot.objects.get(
            produit=self.produit,
            mois=maintenant.month,
            annee=maintenant.year
        )

        self.assertEqual(snapshot.quantite_initiale_reelle, Decimal('10.00'))
        self.assertEqual(snapshot.quantite_finale_reelle, Decimal('12.00'))
        self.assertEqual(snapshot.pamp_historique, Decimal('1000.00'))











from django.urls import reverse
from django.contrib.auth.models import User
class VuesInventaireTestCase(TestCase):

    def setUp(self):
        """Configuration des utilisateurs et des données pour les tests de vues."""
        self.produit = Produit.objects.create(
            nom="Huile d'Argan Premium",
            code="HUILE-ARGAN",
            quantite_stock=Decimal('10.00'),
            quantite_stock_theorique=Decimal('10.00'),
            prix_achat_moyen=Decimal('2500.00'),
            actif=True
        )
        
        self.coiffeur = User.objects.create_user(username="coiffeur_user", password="password123")
        self.gerant = User.objects.create_user(username="gerant_user", password="password123")
        
        # 💡 Si ton décorateur vérifie le statut superuser/staff ou un groupe, on lui donne les accès ici :
        self.gerant.is_staff = True
        self.gerant.is_superuser = True
        self.gerant.save()

    def test_vue_liste_produits_accessible_par_le_gerant(self):
        """Vérifie que la page principale de l'inventaire s'affiche pour le gérant connecté."""
        # ✨ CORRECTION : On connecte le gérant qui possède tous les droits d'accès
        self.client.login(username="gerant_user", password="password123")
        
        url = reverse('inventaire:liste_produits') 
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 200)

    def test_vue_creation_mouvement_bloquee_si_non_connecte(self):
        """Sécurité : Un utilisateur anonyme doit être redirigé s'il tente d'accéder à l'ajout de mouvement."""
        url = reverse('inventaire:ajouter_mouvement', kwargs={'produit_id': self.produit.id}) 
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, 302)

    def test_vue_statistiques_bi_interdite_au_coiffeur(self):
        """Sécurité : Un simple coiffeur ne doit pas avoir accès aux rapports BI."""
        self.client.login(username="coiffeur_user", password="password123")
        
        url = reverse('rapports:dashboard_bi') 
        response = self.client.get(url)
        
        self.assertIn(response.status_code, [302, 403])

    def test_soumission_formulaire_achat_met_a_jour_le_stock(self):
        """Formulaire : Vérifie que poster une nouvelle entrée depuis l'écran fonctionne."""
        self.client.login(username="gerant_user", password="password123")
        
        url = reverse('inventaire:ajouter_mouvement', kwargs={'produit_id': self.produit.id})
        
        # 💡 Ajuste ces clés si les champs de ton formulaire HTML s'appellent autrement 
        # (ex: 'type' au lieu de 'type_mouvement', 'prix' au lieu de 'prix_achat_unitaire')
        data = {
            'produit': self.produit.id,
            'type_mouvement': 'ENTREE',
            'quantite': '5.00',
            'prix_achat_unitaire': '3000.00',
            'notes': 'Nouvel achat via test des vues'
        }
        
        response = self.client.post(url, data)
        
        # Si le formulaire échoue à cause d'une validation, cette ligne affichera l'erreur dans ton terminal
        if response.status_code == 200 and 'form' in response.context:
            print("\n❌ Erreurs du formulaire détectées :", response.context['form'].errors.as_json())
            
        self.assertEqual(response.status_code, 302)
        
        self.produit.refresh_from_db()
        self.assertEqual(self.produit.quantite_stock, Decimal('15.00'))









from django.test import TestCase
from django.urls import reverse
from django.contrib.auth.models import User
from django.utils import timezone
from decimal import Decimal
from .models import Produit, MouvementStock, ChargeExploitation, PaiementCharge

# ==============================================================================
# I. ACCÉLÉRATEUR & SÉCURITÉ DES TESTS LOGIQUES DE MODÈLES (PAMP & DELETE)
# ==============================================================================
class MouvementStockModelTestCase(TestCase):

    def setUp(self):
        """Configuration initiale des entités pour les calculs de PAMP."""
        self.produit = Produit.objects.create(
            nom="Huile d'Argan Pure",
            code="ARGAN-100",
            quantite_stock=Decimal('0.00'),
            quantite_stock_theorique=Decimal('0.00'),
            prix_achat_moyen=Decimal('0.00'),
            seuil_alerte=Decimal('5.00'),
            unite_mesure="ML",
            actif=True
        )

    def test_combinaison_calcul_pamp_et_suppression_relative(self):
        """
        Scénario complexe : Achats successifs, modification du PAMP, 
        puis rollback parfait via la méthode delete().
        """
        mouv1 = MouvementStock.objects.create(
            produit=self.produit,
            type_mouvement='ENTREE',
            quantite=Decimal('10.00'),
            prix_achat_unitaire=Decimal('1000.00'),
            quantite_avant=Decimal('0.00'),
            pamp_historique=Decimal('1000.00'),
            notes="Premier lot"
        )
        self.produit.refresh_from_db()
        
        mouv2 = MouvementStock.objects.create(
            produit=self.produit,
            type_mouvement='ENTREE',
            quantite=Decimal('5.00'),
            prix_achat_unitaire=Decimal('2500.00'),
            quantite_avant=Decimal('10.00'),
            pamp_historique=Decimal('1500.00'),
            notes="Deuxième lot plus cher"
        )
        self.produit.refresh_from_db()

        mouv2.delete()
        self.produit.refresh_from_db()

        self.assertEqual(self.produit.quantite_stock, Decimal('10.00'))
        self.assertEqual(self.produit.prix_achat_moyen, Decimal('1000.00'))


# ==============================================================================
# II. SUITE COMPLÈTE DE TEST DES VUES ET FONCTIONNALITÉS SAAS (BEL'R)
# ==============================================================================
class SuiteCompleteVuesInventaireTestCase(TestCase):

    def setUp(self):
        """Configuration globale des données (Produits, Utilisateurs, Charges)."""
        # 1. Utilisateurs & Permissions SaaS Premium
        self.coiffeur = User.objects.create_user(username="coiffeur_test", password="password123")
        self.gerant = User.objects.create_user(username="gerant_test", password="password123")
        self.gerant.is_staff = True
        self.gerant.is_superuser = True
        self.gerant.save()

        # 2. Catalogue de Stock Initial avec ordonnancement par défaut implicite
        self.produit = Produit.objects.create(
            nom="Shampooing Hydratant Pro",
            code="SHAMP-HYDRA",
            quantite_stock=Decimal('20.00'),
            quantite_stock_theorique=Decimal('20.00'),
            prix_achat_moyen=Decimal('1500.00'),
            seuil_alerte=Decimal('5.00'),
            unite_mesure="BOUTEILLE",
            actif=True
        )

        # 3. Flux de mouvements existants (20 + 10 = 30 initial en stock via signaux)
        self.mouvement = MouvementStock.objects.create(
            produit=self.produit,
            type_mouvement='ENTREE',
            quantite=Decimal('10.00'),
            prix_achat_unitaire=Decimal('1500.00'),
            date_mouvement=timezone.now(),
            notes="Init stock via setUp"
        )

        # 4. Trésorerie & Écritures Comptables Réelles
        self.charge = ChargeExploitation.objects.create(
            type_charge='CAMWATER',
            libelle='Facture Eau Salon Mars',
            montant_total=Decimal('25000.00'),
            date_echeance=timezone.now().date(),
            est_payee=False
        )

        self.paiement = PaiementCharge.objects.create(
            charge=self.charge,
            montant_verse=Decimal('10000.00'),
            date_paiement=timezone.now().date(),
            mode_paiement='MOMO',
            notes='Premier versement partiel'
        )

    # --------------------------------------------------------------------------
    # 1. ACCÈS ET AFFICHAGE DES PAGES (Requêtes GET)
    # --------------------------------------------------------------------------

    def test_vue_liste_produits_accessible(self):
        self.client.login(username="gerant_test", password="password123")
        response = self.client.get(reverse('inventaire:liste_produits'))
        self.assertEqual(response.status_code, 200)

    def test_vue_liste_produits_bi_accessible(self):
        self.client.login(username="gerant_test", password="password123")
        response = self.client.get(reverse('inventaire:liste_produit_bi'))
        self.assertEqual(response.status_code, 200)

    def test_vue_historique_mouvements_global_accessible(self):
        self.client.login(username="gerant_test", password="password123")
        response = self.client.get(reverse('inventaire:historique_mouvements_global'))
        self.assertEqual(response.status_code, 200)

    def test_vue_detail_produit_bi_accessible(self):
        self.client.login(username="gerant_test", password="password123")
        response = self.client.get(reverse('inventaire:detail_produit', kwargs={'produit_id': self.produit.id}))
        self.assertEqual(response.status_code, 200)

    def test_vue_ecran_creation_produit_accessible(self):
        """Vérifie l'accès GET au formulaire de création."""
        self.client.login(username="gerant_test", password="password123")
        response = self.client.get(reverse('inventaire:creer_produit'))
        self.assertEqual(response.status_code, 200)

    def test_vue_ecran_modification_produit_accessible(self):
        """Vérifie l'accès GET au formulaire de modification."""
        self.client.login(username="gerant_test", password="password123")
        response = self.client.get(reverse('inventaire:modifier_produit', kwargs={'pk': self.produit.id}))
        self.assertEqual(response.status_code, 200)

    # --------------------------------------------------------------------------
    # 2. ACTIONS SUR LE CATALOGUE (Validation unifiée via le cycle ORM/Modèles)
    # --------------------------------------------------------------------------

    def test_fonctionnalite_creer_produit(self):
        """Valide la persistance et l'intégrité d'un nouveau produit créé."""
        nouveau_produit = Produit.objects.create(
            nom='Cire Coiffante Premium',
            code='CIRE-PREM',
            quantite_stock=Decimal('0.00'),
            quantite_stock_theorique=Decimal('0.00'),
            prix_achat_moyen=Decimal('2000.00'),
            seuil_alerte=Decimal('5.00'),
            unite_mesure='POT',
            actif=True
        )
        self.assertTrue(Produit.objects.filter(code='CIRE-PREM').exists())
        self.assertEqual(nouveau_produit.nom, 'Cire Coiffante Premium')

    def test_fonctionnalite_modifier_produit(self):
        """Valide la modification de la fiche via l'ORM."""
        self.produit.nom = "Shampooing Hydratant Pro [Édition Limitée]"
        self.produit.save()
        self.produit.refresh_from_db()
        self.assertEqual(self.produit.nom, "Shampooing Hydratant Pro [Édition Limitée]")

    # --------------------------------------------------------------------------
    # 3. ACTIONS SUR LES MOUVEMENTS DE STOCKS (PAMP & Ajustements)
    # --------------------------------------------------------------------------

    def test_fonctionnalite_ajouter_mouvement_pamp(self):
        """Formulaire : Ajout d'un mouvement d'entrée et traitement par les signaux."""
        self.client.login(username="gerant_test", password="password123")
        data = {
            'produit': self.produit.id,
            'type_mouvement': 'ENTREE',
            'quantite': '10.00',
            'prix_achat_unitaire': '1500.00',
            'notes': 'Nouvel arrivage'
        }
        response = self.client.post(reverse('inventaire:ajouter_mouvement', kwargs={'produit_id': self.produit.id}), data)
        self.assertEqual(response.status_code, 302)
        self.produit.refresh_from_db()
        
        # 20 (base) + 10 (setUp) + 10 (POST) = 40.00
        self.assertEqual(self.produit.quantite_stock, Decimal('40.00'))

    def test_fonctionnalite_modifier_mouvement(self):
        """Formulaire : Correction manuelle d'une saisie sur un mouvement de stock."""
        self.client.login(username="gerant_test", password="password123")
        data = {
            'produit': self.produit.id,
            'type_mouvement': 'ENTREE',
            'quantite': '15.00',
            'prix_achat_unitaire': '1500.00',
            'notes': 'Rectification erreur de saisie quantité'
        }
        response = self.client.post(reverse('inventaire:modifier_mouvement', kwargs={'mouvement_id': self.mouvement.id}), data)
        self.assertEqual(response.status_code, 302)
        self.mouvement.refresh_from_db()
        self.assertEqual(self.mouvement.quantite, Decimal('15.00'))

    # --------------------------------------------------------------------------
    # 4. TRÉSORERIE & COMPTABILITÉ (Charges & Factures)
    # --------------------------------------------------------------------------

    def test_fonctionnalite_creer_charge(self):
        self.client.login(username="gerant_test", password="password123")
        data = {
            'type_charge': 'ENEO',
            'libelle': 'Electricité Salon Avril',
            'montant_total': '45000.00',
            'date_echeance': timezone.now().date(),
            'est_payee': False
        }
        response = self.client.post(reverse('inventaire:creer_charge'), data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ChargeExploitation.objects.filter(libelle='Electricité Salon Avril').exists())

    def test_fonctionnalite_modifier_charge(self):
        self.client.login(username="gerant_test", password="password123")
        data = {
            'type_charge': 'CAMWATER',
            'libelle': 'Facture Eau Salon Mars (Ajustée)',
            'montant_total': '28000.00',
            'date_echeance': self.charge.date_echeance,
            'est_payee': False
        }
        response = self.client.post(reverse('inventaire:modifier_charge', kwargs={'pk': self.charge.id}), data)
        self.assertEqual(response.status_code, 302)
        self.charge.refresh_from_db()
        self.assertEqual(self.charge.libelle, 'Facture Eau Salon Mars (Ajustée)')

    def test_fonctionnalite_enregistrer_paiement_charge(self):
        self.client.login(username="gerant_test", password="password123")
        data = {
            'montant_verse': '15000.00',
            'mode_paiement': 'MOMO',
            'date_paiement': timezone.now().date(),
            'notes': 'Règlement partiel'
        }
        url = reverse('inventaire:enregistrer_paiement', kwargs={'charge_id': self.charge.id})
        response = self.client.post(url, data)
        self.assertIn(response.status_code, [200, 302])

    def test_fonctionnalite_modifier_paiement(self):
        self.client.login(username="gerant_test", password="password123")
        data = {
            'charge': self.charge.id,
            'montant_verse': '12000.00',
            'mode_paiement': 'CASH',
            'date_paiement': self.paiement.date_paiement
        }
        url = reverse('inventaire:modifier_paiement', kwargs={'charge_id': self.charge.id, 'paiement_id': self.paiement.id})
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        self.paiement.refresh_from_db()
        self.assertEqual(self.paiement.montant_verse, Decimal('12000.00'))

    def test_fonctionnalite_supprimer_charge(self):
        self.client.login(username="gerant_test", password="password123")
        url = reverse('inventaire:supprimer_charge', kwargs={'pk': self.charge.id})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ChargeExploitation.objects.filter(pk=self.charge.id).exists())

    def test_fonctionnalite_supprimer_paiement(self):
        self.client.login(username="gerant_test", password="password123")
        url = reverse('inventaire:supprimer_paiement', kwargs={'pk': self.paiement.id})
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(PaiementCharge.objects.filter(pk=self.paiement.id).exists())

    # --------------------------------------------------------------------------
    # 5. SÉCURITÉ DE L'ÉTABLISSEMENT & DROITS D'ACCÈS INTER-APPLICATIONS
    # --------------------------------------------------------------------------

    def test_coiffeur_interdit_de_supprimer_des_charges(self):
        self.client.login(username="coiffeur_test", password="password123")
        url = reverse('inventaire:supprimer_charge', kwargs={'pk': self.charge.id})
        response = self.client.post(url)
        self.assertIn(response.status_code, [302, 403])

    def test_vue_statistiques_bi_interdite_au_coiffeur(self):
        self.client.login(username="coiffeur_test", password="password123")
        url = reverse('rapports:dashboard_bi') 
        response = self.client.get(url)
        self.assertIn(response.status_code, [302, 403])




from django.test import TestCase
from django.utils import timezone
from decimal import Decimal
from datetime import datetime
from inventaire.models import Produit, MouvementStock, StockMensuelSnapshot

class TestSnapshotBICloisonnementMultiProduits(TestCase):

    def setUp(self):
        # Produit A : Subira un mouvement en Juin ET en Juillet
        self.produit_A = Produit.objects.create(
            nom="Shampooing Premium BEL'R",
            code="SHAMP01",
            quantite_stock=Decimal('10'),
            quantite_stock_theorique=Decimal('10'),
            prix_achat_moyen=Decimal('15.00'),
            actif=True
        )

        # Produit B : Subira un mouvement en Juin mais RESTERA INACTIF en Juillet
        self.produit_B = Produit.objects.create(
            nom="Soin Kératine BEL'R",
            code="KERAT02",
            quantite_stock=Decimal('5'),
            quantite_stock_theorique=Decimal('5'),
            prix_achat_moyen=Decimal('25.00'),
            actif=True
        )

    def test_mouvement_juillet_produit_a_ne_met_pas_a_zero_produit_b(self):
        """
        S'assure que le premier mouvement du mois de Juillet sur le Produit A
        ne détruit pas et ne passe pas à 0 le PAMP de Juin du Produit B (inactif).
        """
        # =================================================================
        # ÉTAPE 1 : ENREGISTREMENT DE L'ACTIVITÉ DE JUIN (Pour les deux produits)
        # =================================================================
        date_juin = datetime(2026, 6, 20, 14, 0, tzinfo=timezone.get_current_timezone())
        
        # Mouvement Juin - Produit A
        mouv_juin_A = MouvementStock(produit=self.produit_A, type_mouvement='ENTREE', quantite=Decimal('2'), date_mouvement=date_juin)
        mouv_juin_A.date_mouvement = date_juin
        mouv_juin_A.save()

        # Mouvement Juin - Produit B
        mouv_juin_B = MouvementStock(produit=self.produit_B, type_mouvement='ENTREE', quantite=Decimal('1'), date_mouvement=date_juin)
        mouv_juin_B.date_mouvement = date_juin
        mouv_juin_B.save()

        # Vérification initiale : Les deux snapshots de Juin ont le bon PAMP en BDD
        snap_juin_A_avant = StockMensuelSnapshot.objects.get(produit=self.produit_A, mois=6, annee=2026)
        snap_juin_B_avant = StockMensuelSnapshot.objects.get(produit=self.produit_B, mois=6, annee=2026)
        
        self.assertEqual(snap_juin_A_avant.pamp_historique, Decimal('15.00'))
        self.assertEqual(snap_juin_B_avant.pamp_historique, Decimal('25.00'))

        # =================================================================
        # ÉTAPE 2 : LE PASSAGE EN JUILLET (Seul le Produit A bouge, le PAMP change)
        # =================================================================
        self.produit_A.prix_achat_moyen = Decimal('60.00') # Nouvelle entrée très chère pour A
        self.produit_A.save()

        date_juillet = datetime(2026, 7, 2, 9, 0, tzinfo=timezone.get_current_timezone())
        
        # Déclenchement du premier mouvement de Juillet (uniquement sur le Produit A)
        mouv_juillet_A = MouvementStock(produit=self.produit_A, type_mouvement='ENTREE', quantite=Decimal('10'), date_mouvement=date_juillet)
        mouv_juillet_A.date_mouvement = date_juillet
        mouv_juillet_A.save()

        # =================================================================
        # ÉTAPE 3 : VÉRIFICATIONS DE SÉCURITÉ EN BDD
        # =================================================================
        # On recharge l'état des snapshots de Juin depuis la base de données
        snap_juin_A_apres = StockMensuelSnapshot.objects.get(produit=self.produit_A, mois=6, annee=2026)
        snap_juin_B_apres = StockMensuelSnapshot.objects.get(produit=self.produit_B, mois=6, annee=2026)

        # PROTECTION DU PRODUIT B (INACTIF) : Son passé ne doit pas être écrasé à 0 !
        self.assertNotEqual(
            snap_juin_B_apres.pamp_historique, 
            Decimal('0'), 
            "BUG ! Le snapshot de Juin du produit inactif (Produit B) a été réinitialisé ou écrasé à 0 !"
        )
        self.assertEqual(
            snap_juin_B_apres.pamp_historique, 
            Decimal('25.00'), 
            "Le produit inactif a perdu sa valeur PAMP d'origine de Juin."
        )

        # PROTECTION DU PRODUIT A (ACTIF) : Son passé reste également intègre
        self.assertEqual(snap_juin_A_apres.pamp_historique, Decimal('15.00'))