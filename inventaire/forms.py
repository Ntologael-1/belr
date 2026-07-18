from django import forms
from .models import Produit

from django import forms
from django.forms import inlineformset_factory
from .models import Produit, ConsommableService

class ProduitForm(forms.ModelForm):
    class Meta:
        model = Produit
        fields = ['nom', 'code', 'categorie', 'seuil_alerte', 'unite_mesure', 'est_carburant']
        widgets = {
            'nom': forms.TextInput(attrs={'class': 'form-control rounded-3', 'placeholder': 'Ex: Shampoing Keratine'}),
            'code': forms.TextInput(attrs={'class': 'form-control rounded-3'}),
            'categorie': forms.Select(attrs={'class': 'form-select'}),
            'seuil_alerte': forms.NumberInput(attrs={'class': 'form-control'}),
            'unite_mesure': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ml, g, unité'}),
            'est_carburant': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

# Formset pour ajouter les services pendant la création du produit
ConsommableFormSet = inlineformset_factory(
    Produit, 
    ConsommableService,
    fields=['service', 'rendement_par_unite'],
    extra=1, # Une ligne vide par défaut
    can_delete=True,
    widgets={
        'service': forms.Select(attrs={'class': 'form-select'}),
        'rendement_par_unite': forms.NumberInput(attrs={
            'class': 'form-control', 
            'placeholder': 'Nb de fois réalisable avec 1 unité'
        }),
    }
)




from django import forms
from django.forms import inlineformset_factory
from .models import Produit, ConsommableService

# 🚨 Dictionnaire global des messages d'erreur en français
MSG_ERREUR_FR = {
    'required': "Ce champ est obligatoire.",
    'invalid': "La valeur saisie est invalide.",
    'unique': "Cette valeur est déjà utilisée (doit être unique).",
    'max_digits': "Ce nombre comporte trop de chiffres.",
    'invalid_choice': "Veuillez sélectionner un choix valide dans la liste.",
}

class ProduitForm(forms.ModelForm):
    class Meta:
        model = Produit
        fields = ['nom', 'code', 'categorie', 'seuil_alerte', 'unite_mesure', 'est_carburant']
        widgets = {
            'nom': forms.TextInput(attrs={'class': 'form-control rounded-3', 'placeholder': 'Ex: Shampoing Kératine'}),
            'code': forms.TextInput(attrs={'class': 'form-control rounded-3'}),
            'categorie': forms.Select(attrs={'class': 'form-select'}),
            'seuil_alerte': forms.NumberInput(attrs={'class': 'form-control'}),
            'unite_mesure': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ml, g, unité'}),
            'est_carburant': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        # Insertion des messages d'erreur en français pour chaque champ
        error_messages = {
            'nom': MSG_ERREUR_FR,
            'code': MSG_ERREUR_FR,
            'categorie': MSG_ERREUR_FR,
            'seuil_alerte': MSG_ERREUR_FR,
            'unite_mesure': MSG_ERREUR_FR,
        }


# 🚨 Classe de base nécessaire pour injecter le français dans le FormSet inline
class BaseConsommableForm(forms.ModelForm):
    class Meta:
        model = ConsommableService
        fields = ['service', 'rendement_par_unite']
        error_messages = {
            'service': MSG_ERREUR_FR,
            'rendement_par_unite': MSG_ERREUR_FR,
        }


# Ton Formset mis à jour utilisant la classe de base francisée
ConsommableFormSet = inlineformset_factory(
    Produit, 
    ConsommableService,
    form=BaseConsommableForm, # <-- On lie la classe contenant les traductions
    fields=['service', 'rendement_par_unite'],
    extra=1, 
    can_delete=True,
    widgets={
        'service': forms.Select(attrs={'class': 'form-select'}),
        'rendement_par_unite': forms.NumberInput(attrs={
            'class': 'form-control', 
            'placeholder': 'Nb de fois réalisable avec 1 unité'
        }),
    }
)






















from django import forms
from django.forms import inlineformset_factory
from .models import Produit, ConsommableService

MSG_ERREUR_FR = {
    'required': "Ce champ est obligatoire.",
    'invalid': "La valeur saisie est invalide.",
    'unique': "Cette valeur est déjà utilisée (doit être unique).",
    'max_digits': "Ce nombre comporte trop de chiffres.",
    'invalid_choice': "Veuillez sélectionner un choix valide dans la liste.",
}

class ProduitForm(forms.ModelForm):
    class Meta:
        model = Produit
        fields = ['nom', 'code', 'categorie', 'seuil_alerte', 'unite_mesure', 'est_carburant']
        widgets = {
            'nom': forms.TextInput(attrs={'class': 'form-control rounded-3', 'placeholder': 'Ex: Shampoing Kératine'}),
            'code': forms.TextInput(attrs={'class': 'form-control rounded-3'}),
            'categorie': forms.Select(attrs={'class': 'form-select'}),
            'seuil_alerte': forms.NumberInput(attrs={'class': 'form-control'}),
            'unite_mesure': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'ml, g, unité'}),
            'est_carburant': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        error_messages = {
            'nom': MSG_ERREUR_FR,
            'code': MSG_ERREUR_FR,
            'categorie': MSG_ERREUR_FR,
            'seuil_alerte': MSG_ERREUR_FR,
            'unite_mesure': MSG_ERREUR_FR,
        }

    def clean(self):
        cleaned_data = super().clean()
        est_carburant = cleaned_data.get('est_carburant')
        unite_mesure = cleaned_data.get('unite_mesure')

        # Si ce n'est PAS un carburant, l'unité de mesure devient obligatoire
        if not est_carburant and not unite_mesure:
            self.add_error('unite_mesure', MSG_ERREUR_FR['required'])
            
        return cleaned_data


# Formulaire de base pour le FormSet afin de forcer les validations personnalisées
class BaseConsommableForm(forms.ModelForm):
    class Meta:
        model = ConsommableService
        fields = ['service', 'rendement_par_unite']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Supprime la valeur par défaut
        self.fields['rendement_par_unite'].initial = None
        
        # Force les attributs HTML requis et supprime les placeholders trompeurs
        self.fields['service'].required = True
        self.fields['rendement_par_unite'].required = True
        
        # Ajoute l'attribut HTML "required" pour forcer la détection
        self.fields['service'].widget.attrs['required'] = 'required'
        self.fields['rendement_par_unite'].widget.attrs['required'] = 'required'

# Création du FormSet basé sur notre formulaire personnalisé
ConsommableFormSet = inlineformset_factory(
    Produit, 
    ConsommableService,
    form=BaseConsommableForm, # Utilisation du formulaire personnalisé ci-dessus
    fields=['service', 'rendement_par_unite'],
    extra=1, 
    can_delete=True,
    widgets={
        'service': forms.Select(attrs={'class': 'form-select'}),
        'rendement_par_unite': forms.NumberInput(attrs={
            'class': 'form-control', 
            'placeholder': 'Nb de fois réalisable (Ex: 10)'
        }),
    },
    error_messages={
        'service': MSG_ERREUR_FR,
        'rendement_par_unite': MSG_ERREUR_FR,
    }
)











from django import forms
from .models import ChargeExploitation, PaiementCharge

class ChargeExploitationForm(forms.ModelForm):
    class Meta:
        model = ChargeExploitation
        fields = ['type_charge', 'libelle', 'montant_total', 'date_echeance']
        widgets = {
            'date_echeance': forms.DateInput(attrs={'type': 'date', 'class': 'form-control rounded-pill'}),
            'type_charge': forms.Select(attrs={'class': 'form-select rounded-pill'}),
            'libelle': forms.TextInput(attrs={'class': 'form-control rounded-pill', 'placeholder': 'Ex: Loyer Mai 2026'}),
            'montant_total': forms.NumberInput(attrs={'class': 'form-control rounded-pill', 'placeholder': 'Montant en FCFA'}),
        }

class PaiementChargeForm(forms.ModelForm):
    class Meta:
        model = PaiementCharge
        fields = ['montant_verse', 'mode_paiement', 'notes', 'recu_image']
        widgets = {
            'montant_verse': forms.NumberInput(attrs={'class': 'form-control rounded-pill'}),
            'mode_paiement': forms.Select(attrs={'class': 'form-select rounded-pill'}),
            'notes': forms.Textarea(attrs={'class': 'form-control rounded-4', 'rows': 3}),
            'recu_image': forms.FileInput(attrs={'class': 'form-control'}),
        }