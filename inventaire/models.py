from django.db import models

# Create your models here.
from django.core.validators import MinValueValidator



from django.db import models
from django.db.models import Sum, F
from django.core.validators import MinValueValidator
from django.contrib.auth import get_user_model
from decimal import Decimal
from django.utils import timezone

User = get_user_model()







import uuid
from decimal import Decimal
from django.db import models, transaction
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator
from django.utils import timezone
from django.core.exceptions import ValidationError

class CategorieProduit(models.Model):
    nom = models.CharField(max_length=100)
    description = models.TextField(blank=True)
   

    class Meta:
        verbose_name_plural = "Catégories Produits"

    def __str__(self):
        return self.nom

# class Produit(models.Model):
#     nom = models.CharField(max_length=200)
#     code = models.CharField(max_length=50, unique=True, blank=True, null=True, db_index=True)
#     categorie = models.ForeignKey(CategorieProduit, on_delete=models.CASCADE, related_name='produits', null=True, blank=True)
    
#     # Stock
#     quantite_stock = models.DecimalField(max_digits=10, decimal_places=2, default=0)
#     quantite_stock_theorique = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Stock Théorique")
#     seuil_alerte = models.DecimalField(max_digits=10, decimal_places=2, default=5)
#     unite_mesure = models.CharField(max_length=20, default="unité")
    
#     # Finances
#     prix_achat_moyen = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="PAMP")
#     dernier_prix_achat = models.DecimalField(max_digits=10, decimal_places=2, default=0)
#     valeur_stock_totale = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
#     est_carburant = models.BooleanField(default=False, help_text="Cochez si c'est du carburant pour le générateur")
#     actif = models.BooleanField(default=True, db_index=True) # Indexé pour filtrer rapidement les produits au catalogue
#     updated_at = models.DateTimeField(auto_now=True)

#     class Meta:
#         indexes = [
#             models.Index(fields=['actif', 'code']),
#         ]


#     class Meta:
#         ordering = ['nom']

#     def __str__(self):
#         return self.nom

#     @property
#     def est_en_alerte(self):
#         return self.quantite_stock <= self.seuil_alerte
    
#     @property
#     def valeur_stock_theorique(self):
#         return (self.quantite_stock_theorique or 0) * (self.prix_achat_moyen or 0)





from django.db import models
from django.db.models import Sum, Q, Case, When, BooleanField
from django.utils import timezone

# class ProduitQuerySet(models.QuerySet):
#     def avec_metriques_bi(self, mois=None, annee=None):
#         """
#         Annote le QuerySet avec :
#         1. 'est_en_alerte_db' : Évalué au niveau SQL basé sur le stock réel physique.
#         2. 'quantite_consumed' : Le volume des sorties (consommations/ventes) sur le mois/année cible.
#         """
#         maintenant = timezone.now()
#         mois_cible = mois or maintenant.month
#         annee_cible = annee or maintenant.year
        
#         return self.annotate(
#             # Évaluation de l'alerte directement en SQL pour permettre le tri natif
#             est_en_alerte_db=Case(
#                 When(quantite_stock__lte=models.F('seuil_alerte'), then=True),
#                 default=False,
#                 output_field=BooleanField()
#             ),
#             # Calcul des sorties (Utilisation des vrais noms de champs : 'date_mouvement' et 'type_mouvement')
#             quantite_consumed=Sum(
#                 'mouvements__quantite',
#                 filter=Q(
#                     mouvements__date_mouvement__month=mois_cible,
#                     mouvements__date_mouvement__year=annee_cible,
#                     mouvements__type_mouvement='SORTIE' 
#                 )
#             )
#         )

#     def classer_selon_critere(self, critere, mois=None, annee=None):
#         """
#         Applique les classements dynamiques demandés :
#         - 'nom' : Ordre alphabétique
#         - 'alerte' : Les produits en crise d'abord
#         - 'consommation' : Les plus utilisés/sortis d'abord
#         - 'recent' : Les plus récemment créés d'abord
#         """
#         # On s'assure d'abord d'avoir les annotations nécessaires
#         qs = self.avec_metriques_bi(mois=mois, annee=annee)
        
#         if critere == 'alerte':
#             return qs.order_by('-est_en_alerte_db', 'nom')
#         elif critere == 'consommation':
#             # On utilise Coalesce ou on trie en mettant les valeurs nulles (0 sortie) à la fin
#             return qs.order_by('-quantite_consumed', 'nom')
#         elif critere == 'recent':
#             return qs.order_by('-created_at', 'nom')
#         else:
#             # Tri par défaut par nom
#             return qs.order_by('nom')
from django.db.models.functions import Coalesce
from django.db.models import OuterRef, Subquery, Sum, Case, When, BooleanField

class ProduitQuerySet(models.QuerySet):
    def avec_metriques_bi(self, mois=None, annee=None):
        """
        Annote le QuerySet de manière isolée pour éviter les produits cartésiens (doublons SQL).
        """
        maintenant = timezone.now()
        mois_cible = mois or maintenant.month
        annee_cible = annee or maintenant.year
        
        # ✅ SOLUTION: On calcule la somme dans une Subquery isolée
        # Cela empêche SQL de dupliquer les lignes du produit principal !
        subquery_conso = MouvementStock.objects.filter(
            produit_id=OuterRef('pk'),
            date_mouvement__month=mois_cible,
            date_mouvement__year=annee_cible,
            type_mouvement='SORTIE'
        ).values('produit_id').annotate(total=Sum('quantite')).values('total')

        return self.annotate(
            # Évaluation de l'alerte directe
            est_en_alerte_db=Case(
                When(quantite_stock__lte=models.F('seuil_alerte'), then=True),
                default=False,
                output_field=BooleanField()
            ),
            # Utilisation de la Subquery sécurisée à la place du Sum() direct
            quantite_consumed=Coalesce(Subquery(subquery_conso[:1]), Decimal('0'))
        )

    def classer_selon_critere(self, critere, mois=None, annee=None):
        """
        Applique les classements dynamiques demandés.
        """
        qs = self.avec_metriques_bi(mois=mois, annee=annee)
        
        if critere == 'alerte':
            return qs.order_by('-est_en_alerte_db', 'nom')
        elif critere == 'consommation':
            return qs.order_by('-quantite_consumed', 'nom')
        elif critere == 'recent':
            return qs.order_by('-created_at', 'nom')
        else:
            return qs.order_by('nom')


class Produit(models.Model):
    nom = models.CharField(max_length=200)
    code = models.CharField(max_length=50, unique=True, blank=True, null=True, db_index=True)
    categorie = models.ForeignKey('CategorieProduit', on_delete=models.CASCADE, related_name='produits', null=True, blank=True)
    
    # Stock
    quantite_stock = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    quantite_stock_theorique = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="Stock Théorique")
    seuil_alerte = models.DecimalField(max_digits=10, decimal_places=2, default=5)
    unite_mesure = models.CharField(max_length=20, default="unité")
    
    # Finances
    prix_achat_moyen = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name="PAMP")
    dernier_prix_achat = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    valeur_stock_totale = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    est_carburant = models.BooleanField(default=False, help_text="Cochez si c'est du carburant pour le générateur")
    actif = models.BooleanField(default=True, db_index=True) 
    
    # Suivi temporel (indispensable pour le tri par nouveauté)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Branchement du Custom Manager
    objects = ProduitQuerySet.as_manager()

    class Meta:
        indexes = [
            models.Index(fields=['actif', 'code']),
            models.Index(fields=['created_at']),
        ]
        ordering = ['nom'] # Classement par défaut au niveau global de Django

    def __str__(self):
        return self.nom

    @property
    def est_en_alerte(self):
        """ Conservé pour la compatibilité avec tes anciens templates Python """
        return self.quantite_stock <= self.seuil_alerte
    
    @property
    def valeur_stock_theorique(self):
        return (self.quantite_stock_theorique or 0) * (self.prix_achat_moyen or 0)

class MouvementStock(models.Model):
    TYPE_CHOICES = [
        ('ENTREE', 'Entrée (Achat)'),
        ('SORTIE', 'Sortie (Utilisation)'),
        ('AJUSTEMENT', 'Ajustement Inventaire'),
    ]

    produit = models.ForeignKey(Produit, on_delete=models.CASCADE, related_name='mouvements')
    type_mouvement = models.CharField(max_length=15, choices=TYPE_CHOICES, db_index=True)
    quantite = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0.01)])
    prix_achat_unitaire = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    pamp_historique = models.DecimalField(max_digits=10, decimal_places=2, default=0, editable=False)
    
    # Audit
    quantite_avant = models.DecimalField(max_digits=10, decimal_places=2, editable=False)
    quantite_apres = models.DecimalField(max_digits=10, decimal_places=2, editable=False)
    
    date_mouvement = models.DateTimeField(auto_now_add=True, db_index=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    notes = models.TextField(blank=True)
    is_automatique = models.BooleanField(default=False, help_text="Vrai si généré par un paiement")
    
    # Champs BI
    quantite_theorique = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    quantite_reelle = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        ordering = ['-date_mouvement']
        indexes = [
            models.Index(fields=['produit', 'date_mouvement']),
            models.Index(fields=['type_mouvement', 'date_mouvement']),
        ]

    def __str__(self):
        return f"{self.type_mouvement} - {self.produit.nom} ({self.quantite})"
    
    



    def _preparer_champs_analyse(self):
        """Responsabilité 1 : Gestion des champs de quantité pour la BI."""
        if self.is_automatique:
            self.quantite_theorique = self.quantite
            self.quantite_reelle = 0
        else:
            self.quantite_reelle = self.quantite
            self.quantite_theorique = 0

    def _annuler_ancien_mouvement(self):
        """Responsabilité 2 : Annulation de l'ancien état en cas de MODIFICATION."""
        ancien_mouvement = MouvementStock.objects.get(pk=self.pk)
        if ancien_mouvement.type_mouvement == 'ENTREE':
            self.produit.quantite_stock -= ancien_mouvement.quantite
            self.produit.quantite_stock_theorique -= ancien_mouvement.quantite
        elif ancien_mouvement.type_mouvement == 'SORTIE':
            if ancien_mouvement.is_automatique:
                self.produit.quantite_stock_theorique += ancien_mouvement.quantite
            else:
                self.produit.quantite_stock = ancien_mouvement.quantite_avant

    def _recalculer_pamp(self):
        """Responsabilité 3 : Calcul mathématique du Prix d'Achat Moyen Pondéré (PAMP)."""
        if self.prix_achat_unitaire and self.prix_achat_unitaire > 0:
            valeur_actuelle = self.quantite_avant * self.produit.prix_achat_moyen
            valeur_nouvelle = self.quantite * self.prix_achat_unitaire
            nouvelle_qte_total = self.quantite_avant + self.quantite
            
            if nouvelle_qte_total > 0:
                self.produit.prix_achat_moyen = (valeur_actuelle + valeur_nouvelle) / nouvelle_qte_total
            else:
                self.produit.prix_achat_moyen = self.prix_achat_unitaire
            self.produit.dernier_prix_achat = self.prix_achat_unitaire

    def _appliquer_mouvements_stock(self):
        """Responsabilité 4 : Application des règles métiers selon le type de mouvement."""
        if self.type_mouvement == 'ENTREE':
            self.produit.quantite_stock += self.quantite
            self.produit.quantite_stock_theorique += self.quantite
            self._recalculer_pamp()
            
        elif self.type_mouvement == 'SORTIE':
            if self.is_automatique:
                self.produit.quantite_stock_theorique -= self.quantite
            else:
                # Saisie Manager (Inventaire de contrôle)
                self.produit.quantite_stock = self.quantite

        elif self.type_mouvement == 'AJUSTEMENT':
            self.produit.quantite_stock = self.quantite
            self.produit.quantite_stock_theorique = self.quantite

    def _mettre_a_jour_snapshot_bi(self, is_new):
        """Responsabilité 5 : Clôture et mise à jour du Snapshot BI de fin de mois."""
        maintenant = timezone.now()
        # current_month = self.date_mouvement.month if not is_new else maintenant.month
        # current_year = self.date_mouvement.year if not is_new else maintenant.year
        # # Remplacement sécurisé dans ton modèle MouvementStock :
        current_month = self.date_mouvement.month
        current_year = self.date_mouvement.year
        snapshot, created = StockMensuelSnapshot.objects.get_or_create(
            produit=self.produit,
            mois=current_month,
            annee=current_year,
            defaults={
                'quantite_initiale_reelle': self.quantite_avant,
                'quantite_initiale_theorique': self.produit.quantite_stock_theorique,
            }
        )

        snapshot.pamp_historique = self.produit.prix_achat_moyen
        snapshot.quantite_finale_reelle = self.produit.quantite_stock
        snapshot.quantite_finale_theorique = self.produit.quantite_stock_theorique
        snapshot.save()

    def save(self, *args, **kwargs):
        """Le chef d'orchestre : méthode principale atomique et hautement lisible."""
        is_new = self.pk is None 

        self._preparer_champs_analyse()

        if not is_new:
            self._annuler_ancien_mouvement()

        # Préparation de l'audit
        self.quantite_avant = self.produit.quantite_stock
        self.clean()

        # Calculs et modifications des stocks du produit lié
        self._appliquer_mouvements_stock()

        # Finalisation des données financières du mouvement
        self.pamp_historique = self.produit.prix_achat_moyen
        self.quantite_apres = self.produit.quantite_stock
        self.produit.valeur_stock_totale = self.produit.quantite_stock * self.produit.prix_achat_moyen

        # Sauvegarde sécurisée dans une transaction atomique Django
        with transaction.atomic():
            if self.produit.pk:
                self.produit.save()

            super().save(*args, **kwargs)
            self.produit.refresh_from_db()
            
            self._mettre_a_jour_snapshot_bi(is_new)


    def clean(self):
        """
        Validation des règles métiers avant la sauvegarde dans la base de données.
        """
        super().clean()
        
        # 🔐 SÉCURITÉ À LA SAISIE : Bloquer les inventaires aberrants
        if self.type_mouvement == 'SORTIE' and not self.is_automatique:
            # On récupère le stock actuel avant d'appliquer ce mouvement
            # Si le mouvement existe déjà (modification), on prend sa valeur quantite_avant
            stock_disponible = self.quantite_avant if self.pk else self.produit.quantite_stock
            
            # self.quantite représente ici le "Reste en stock" déclaré par le manager
            if self.quantite > stock_disponible:
                raise ValidationError({
                    'quantite': (
                       f"Impossible : Le reste déclaré ({self.quantite}) dépasse le stock disponible ({stock_disponible})."
                    )
                })

    


    def delete(self, *args, **kwargs):
        """
        Garde-fou chronologique à la suppression et restauration relative du stock.
        """
        # 1. 🔐 SÉCURITÉ : Bloquer le désordre chronologique pour les inventaires manuels
        if self.type_mouvement == 'SORTIE' and not self.is_automatique:
            if MouvementStock.objects.filter(
                produit=self.produit,
                type_mouvement='SORTIE',
                is_automatique=False,
                date_mouvement__gt=self.date_mouvement
            ).exists():
                raise ValidationError("Action refusée : Un inventaire plus récent bloque la suppression de celui-ci.")

        produit_concerne = self.produit
        type_mouv = self.type_mouvement
        qte_mouv = self.quantite

        # 2. 📉 LOGIQUE DE RESTAURATION RELATIVE DES STOCKS
        if type_mouv == 'ENTREE':
            produit_concerne.quantite_stock -= qte_mouv
            produit_concerne.quantite_stock_theorique -= qte_mouv
            
            # Recherche de l'entrée immédiatement précédente
            derniere_entree = MouvementStock.objects.filter(
                produit=produit_concerne, 
                type_mouvement='ENTREE'
            ).exclude(pk=self.pk).order_by('date_mouvement').last()
            
            if derniere_entree:
                produit_concerne.prix_achat_moyen = derniere_entree.pamp_historique
                produit_concerne.dernier_prix_achat = derniere_entree.prix_achat_unitaire
            elif produit_concerne.quantite_stock <= 0:
                produit_concerne.prix_achat_moyen = Decimal('0')
            elif self.quantite_avant > 0:
                # 🧮 Rollback financier de l'unique entrée pour retrouver le PAMP d'origine
                valeur_totale_apres = (self.quantite_avant + qte_mouv) * self.pamp_historique
                valeur_achat = qte_mouv * (self.prix_achat_unitaire or Decimal('0'))
                produit_concerne.prix_achat_moyen = (valeur_totale_apres - valeur_achat) / self.quantite_avant

        elif type_mouv == 'SORTIE':
            if self.is_automatique:
                produit_concerne.quantite_stock_theorique += qte_mouv
            else:
                # Restauration de l'écart constaté lors de l'inventaire manuel
                quantite_perdue = self.quantite_avant - qte_mouv
                if quantite_perdue > 0:
                    produit_concerne.quantite_stock += quantite_perdue

        elif type_mouv == 'AJUSTEMENT':
            ecart = self.quantite_avant - qte_mouv
            produit_concerne.quantite_stock += ecart
            produit_concerne.quantite_stock_theorique += ecart

        # 3. 💾 MISE À JOUR FINANCIÈRE ET SAUVEGARDE DU PRODUIT
        produit_concerne.valeur_stock_totale = produit_concerne.quantite_stock * produit_concerne.prix_achat_moyen
        produit_concerne.save()

        # 4. 📊 BI : SYNCHRONISATION DU SNAPSHOT MENSUEL
        mois_mouv = self.date_mouvement.month if self.date_mouvement else timezone.now().month
        annee_mouv = self.date_mouvement.year if self.date_mouvement else timezone.now().year

        StockMensuelSnapshot.objects.filter(
            produit=produit_concerne, mois=mois_mouv, annee=annee_mouv
        ).update(
            quantite_finale_reelle=produit_concerne.quantite_stock,
            quantite_finale_theorique=produit_concerne.quantite_stock_theorique,
            pamp_historique=produit_concerne.prix_achat_moyen
        )

        # 5. ❌ SUPPRESSION PHYSIQUE DU MOUVEMENT
        super().delete(*args, **kwargs)














    



class ConsommableService(models.Model):
    # 'gestion.Service' référencé de manière sécurisée en string
    service = models.ForeignKey('gestion.Service', on_delete=models.CASCADE, related_name='recette')
    produit = models.ForeignKey(Produit, on_delete=models.CASCADE, related_name='utilisations_services')
    rendement_par_unite = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    quantite_prevue = models.DecimalField(max_digits=10, decimal_places=5, default=0)

    def save(self, *args, **kwargs):
        if self.rendement_par_unite > 0:
            self.quantite_prevue = Decimal('1') / self.rendement_par_unite
        super().save(*args, **kwargs)

    @property
    def cout_estime(self):
        return self.quantite_prevue * self.produit.prix_achat_moyen


class ChargeExploitation(models.Model):
    TYPE_CHARGE = [
        ('LOYER', 'Loyer du Salon'),
        ('ENEO', 'Électricité (ENEO)'),
        ('CAMWATER', 'Eau (CAMWATER)'),
        ('INTERNET', 'Abonnement Internet'),
        ('SALAIRE_FIXE', 'Salaire Fixe (Non commissionné)'),
        ('IMPOT', 'Impôts et Taxes'),
        ('DIVERS', 'Divers / Autres'),
    ]

    type_charge = models.CharField(max_length=20, choices=TYPE_CHARGE, db_index=True)
    libelle = models.CharField(max_length=255)
    montant_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    date_echeance = models.DateField(default=timezone.now, db_index=True)
    est_payee = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.libelle} - {self.montant_total} FCFA"

    @property
    def montant_paye(self):
        return self.paiements.aggregate(models.Sum('montant_verse'))['montant_verse__sum'] or Decimal('0')

    @property
    def reste_a_payer(self):
        return self.montant_total - self.montant_paye


class PaiementCharge(models.Model):
    MODE_PAIEMENT = [
        ('CASH', 'Espèces'),
        ('OM', 'Orange Money'),
        ('MOMO', 'MTN MoMo'),
        ('VIREMENT', 'Virement'),
    ]

    charge = models.ForeignKey(ChargeExploitation, on_delete=models.CASCADE, related_name='paiements')
    montant_verse = models.DecimalField(max_digits=12, decimal_places=2)
    date_paiement = models.DateField(default=timezone.now)
    mode_paiement = models.CharField(max_length=20, choices=MODE_PAIEMENT)
    recu_image = models.ImageField(upload_to='recus_charges/', null=True, blank=True)
    notes = models.TextField(blank=True)

    @transaction.atomic
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Re-calcul automatique propre via l'instance rafraîchie de sa charge mère
        if self.charge.reste_a_payer <= 0:
            self.charge.est_payee = True
            self.charge.save()


class StockMensuelSnapshot(models.Model):
    produit = models.ForeignKey(Produit, on_delete=models.CASCADE, related_name='stocks_initiaux')
    mois = models.PositiveSmallIntegerField()
    annee = models.PositiveIntegerField()
    
    quantite_initiale_reelle = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    quantite_initiale_theorique = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    quantite_finale_reelle = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    quantite_finale_theorique = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    pamp_historique = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    class Meta:
        unique_together = ('produit', 'mois', 'annee')
        indexes = [
            models.Index(fields=['annee', 'mois']), # Pour accélérer les filtres de rapports globaux par date
        ]

    def __str__(self):
        return f"{self.produit.nom} - {self.mois}/{self.annee}"

    @classmethod
    def supprimer_snapshot(cls, produit, mois, annee):
        return cls.objects.filter(produit=produit, mois=mois, annee=annee).delete()[0] > 0

    @classmethod
    def vider_tout_le_mois(cls, mois, annee):
        return cls.objects.filter(mois=mois, annee=annee).delete()[0]
    


class DosageHistorique(models.Model):
    produit = models.ForeignKey('Produit', on_delete=models.CASCADE, related_name='historique_dosages')
    service = models.ForeignKey('gestion.Service', on_delete=models.CASCADE)
    quantite_figee = models.DecimalField(max_digits=10, decimal_places=2)
    mois = models.IntegerField()
    annee = models.IntegerField()

    class Meta:
        # Sécurité : Une seule ligne par couple produit/service pour un mois donné
        unique_together = ('produit', 'service', 'mois', 'annee')


