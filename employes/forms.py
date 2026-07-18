from django import forms
from django.contrib.auth.models import User, Group
from .models import Employe
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError  # <-- AJOUTEZ CETTE LIGNE






class UserForm(forms.ModelForm):
    # Champ personnalisé pour choisir le rôle (Groupe Django)
    role = forms.ModelChoiceField(
        queryset=Group.objects.all(),
        required=True,
        label="Rôle / Autorisation d'accès",
        widget=forms.Select(attrs={'class': 'form-select'}),
        empty_label="-- Sélectionner un rôle --"
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'role']
        labels = {
            'first_name': 'Prénom',
            'last_name': 'Nom',
        }
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control', 'placeholder': "Nom d'utilisateur"}),
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Prénom'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nom'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'exemple@email.com'}),
        }

    def __init__(self, *args, **kwargs):
        """Initialisation du formulaire utilisateur"""
        super().__init__(*args, **kwargs)
        # 🛠️ Pré-sélection du rôle existant si on est en mode modification (édition)
        if self.instance and self.instance.pk:
            actuel_group = self.instance.groups.first()
            if actuel_group:
                self.initial['role'] = actuel_group.pk

    def clean_username(self):
        """Validation du nom d'utilisateur avec exclusion de l'instance actuelle"""
        username = self.cleaned_data.get('username')
        if User.objects.filter(username=username).exclude(pk=self.instance.pk).exists():
            raise ValidationError("Ce nom d'utilisateur est déjà utilisé par un autre membre.")
        return username

    def clean_email(self):
        """Validation de l'adresse email avec exclusion de l'instance actuelle"""
        email = self.cleaned_data.get('email')
        if email:
            if User.objects.filter(email=email).exclude(pk=self.instance.pk).exists():
                raise ValidationError("Cette adresse email est déjà associée à un autre compte.")
        return email


class EmployeForm(forms.ModelForm):
    JOURS_CHOICES = [
        ('Lundi', 'Lundi'), ('Mardi', 'Mardi'), ('Mercredi', 'Mercredi'),
        ('Jeudi', 'Jeudi'), ('Vendredi', 'Vendredi'), ('Samedi', 'Samedi'), ('Dimanche', 'Dimanche')
    ]

    # Champ de sélection multiple personnalisé pour le planning
    jours_travail = forms.MultipleChoiceField(
        choices=JOURS_CHOICES,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
        required=False,
        label="Jours de travail"
    )

    class Meta:
        model = Employe
        fields = '__all__'
        exclude = ['user', 'actif']  # 'user' et 'actif' sont gérés directement au niveau de la vue (views.py)
        widgets = {
            # Dates et Heures
            'date_embauche': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'date_fin_contrat': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'heure_debut': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'heure_fin': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            
            # Paramètres financiers & commissions
            'salaire_base': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Ex: 50000'}),
            'palier_1_ca': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Ex: 200000'}),
            'palier_1_percent': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Ex: 5'}),
            'palier_2_ca': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Ex: 500000'}),
            'palier_2_percent': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Ex: 10'}),
            
            # Fiche d'identité professionnelle
            'matricule': forms.TextInput(attrs={'class': 'form-control'}),
            'specialite': forms.TextInput(attrs={'class': 'form-control'}),
            'type_contrat': forms.Select(attrs={'class': 'form-select'}),
            'telephone': forms.TextInput(attrs={'class': 'form-control'}),
            'couleur_calendrier': forms.TextInput(attrs={'type': 'color', 'class': 'form-control form-control-color w-100'}),
        }

    # def __init__(self, *args, **kwargs):
    #     """Initialisation du formulaire employé"""
    #     super().__init__(*args, **kwargs)
    #     # 🛠️ Restitution et découpage des jours cochés enregistrés sous forme de chaîne de caractères
    #     if self.instance and self.instance.pk and getattr(self.instance, 'jours_travail', None):
    #         self.initial['jours_travail'] = self.instance.jours_travail.split(',')
    def __init__(self, *args, **kwargs):
        """Initialisation du formulaire employé"""
        super().__init__(*args, **kwargs)
        
        # 🛠️ Restitution et découpage des jours cochés enregistrés
        if self.instance and self.instance.pk and getattr(self.instance, 'jours_travail', None):
            self.initial['jours_travail'] = self.instance.jours_travail.split(',')

        # Liste de tes champs financiers d'après ton modèle
        champs_paliers = [
            'salaire_base', 
            'palier_1_ca', 
            'palier_1_percent', 
            'palier_2_ca', 
            'palier_2_percent'
        ]

        for champ in champs_paliers:
            if champ in self.fields:
                # 1. Rendre le champ obligatoirement requis à la soumission
                self.fields[champ].required = True
                
                # 2. Forcer la valeur initiale à vide (None) UNIQUEMENT à la création
                if not self.instance or not self.instance.pk:
                    self.fields[champ].initial = None

    def clean_jours_travail(self):
        """Transformation de la liste des jours sélectionnés en chaîne de caractères séparée par des virgules"""
        jours_liste = self.cleaned_data.get('jours_travail')
        return ",".join(jours_liste) if jours_liste else ""