from django.db import models

# Create your models here.

from django.db import models
from django.contrib.auth.models import User

# ─── SNAPSHOT DES PERFORMANCES SALARIALES ───
class PerformanceMensuelleSnapshot(models.Model):
    employe = models.ForeignKey('employes.Employe', on_delete=models.CASCADE, related_name='performances_mensuelles')
    mois = models.PositiveSmallIntegerField()  # 1 à 12
    annee = models.PositiveIntegerField()
    
    # Rémunération et paliers figés pour ce mois précis
    salaire_base_historique = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    palier_1_ca_historique = models.DecimalField(max_digits=12, decimal_places=2, default=200000)
    palier_1_percent_historique = models.IntegerField(default=5)
    palier_2_ca_historique = models.DecimalField(max_digits=12, decimal_places=2, default=500000)
    palier_2_percent_historique = models.IntegerField(default=10)

    class Meta:
        unique_together = ('employe', 'mois', 'annee')

    def __str__(self):
        return f"{self.employe.nom_complet} - Photo Salaire {self.mois}/{self.annee}"


# ─── SNAPSHOT DES DOSAGES PRODUITS (RECETTES) ───
class DosageMensuelSnapshot(models.Model):
    produit = models.ForeignKey('inventaire.Produit', on_delete=models.CASCADE, related_name='dosages_mensuels')
    service = models.ForeignKey('gestion.Service', on_delete=models.CASCADE)
    mois = models.PositiveSmallIntegerField()  # 1 à 12
    annee = models.PositiveIntegerField()
    
    # Quantité prévue (1 / rendement) figée pour ce mois précis
    quantite_prevue_historique = models.DecimalField(max_digits=10, decimal_places=5, default=0)
    rendement_par_unite_historique = models.DecimalField(max_digits=10, decimal_places=2, default=1)

    class Meta:
        unique_together = ('produit', 'service', 'mois', 'annee')

    def __str__(self):
        return f"Dosage {self.produit.nom} -> {self.service.nom} ({self.mois}/{self.annee})"
    





from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator

class RapportMensuelConsolide(models.Model):
    """
    Modèle d'agrégation stockant les indicateurs clés par mois et par année.
    Sert de base de données rapide pour les calculs d'effet ciseau, 
    les évolutions de CA d'une année sur l'autre (N vs N-1) et les graphiques.
    """
    annee = models.IntegerField(
        validators=[MinValueValidator(2020), MaxValueValidator(2099)],
        verbose_name="Année"
    )
    # 1 = Janvier, 12 = Décembre
    mois = models.IntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(12)],
        verbose_name="Mois"
    )
    
    # Indicateurs de Chiffre d'Affaires (CA)
    chiffre_affaires = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0.00,
        verbose_name="Chiffre d'Affaires Total"
    )
    
    # Indicateurs de Charges / Coûts Généraux
    couts_generaux = models.DecimalField(
        max_digits=12, 
        decimal_places=2, 
        default=0.00,
        verbose_name="Coûts Généraux (Charges, Achats Stocks, Proratas)"
    )
    
    # Métriques de volume pour affiner l'effet ciseau (Optionnel mais recommandé)
    nombre_fiches_traitees = models.IntegerField(
        default=0,
        verbose_name="Nombre de fiches cabines"
    )
    
    date_mise_a_jour = models.DateTimeField(
        auto_now=True,
        verbose_name="Dernière consolidation"
    )

    class Meta:
        verbose_name = "Rapport Mensuel Consolidé"
        verbose_name_plural = "Rapports Mensuels Consolidés"
        # Empêche d'avoir deux lignes pour le même mois de la même année
        unique_together = ('annee', 'mois')
        ordering = ['-annee', '-mois']

    def __str__(self):
        return f"Consolidation {self.mois:02d}/{self.annee}"

    # --- MÉTHODES DE CALCUL POUR LA VUE (LOGIQUE ANNUELLE / N-1) ---

    def get_correspondant_annee_precedente(self):
        """Récupère l'enregistrement du même mois de l'année N-1"""
        return RapportMensuelConsolide.objects.filter(
            annee=self.annee - 1, 
            mois=self.mois
        ).first()

    @property
    def evolution_chiffre_affaires_pct(self):
        """Calcule le % d'évolution du CA par rapport au mois correspondant N-1"""
        precedent = self.get_correspondant_annee_precedente()
        if not precedent or precedent.chiffre_affaires == 0:
            return 0.0
        
        # Formule : ((CA_N - CA_N-1) / CA_N-1) * 100
        evolution = ((self.chiffre_affaires - precedent.chiffre_affaires) / precedent.chiffre_affaires) * 100
        return round(float(evolution), 2)

    @property
    def evolution_couts_pct(self):
        """Calcule le % d'évolution des coûts généraux par rapport au mois correspondant N-1"""
        precedent = self.get_correspondant_annee_precedente()
        if not precedent or precedent.couts_generaux == 0:
            return 0.0
            
        evolution = ((self.couts_generaux - precedent.couts_generaux) / precedent.couts_generaux) * 100
        return round(float(evolution), 2)

    @property
    def effet_ciseau(self):
        """
        Calcule l'effet ciseau.
        Formule standard : % Évolution du CA - % Évolution des Charges.
        - Si Positif (> 0) : Effet ciseau favorable (le CA augmente plus vite que les coûts).
        - Si Négatif (< 0) : Effet ciseau défavorable (les coûts augmentent plus vite que le CA).
        """
        # S'il n'y a pas de mois correspondant à l'année précédente, l'effet ciseau n'est pas calculable (0)
        if not self.get_correspondant_annee_precedente():
            return 0.0
            
        return round(self.evolution_chiffre_affaires_pct - self.evolution_couts_pct, 2)