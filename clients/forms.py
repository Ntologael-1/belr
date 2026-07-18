from django import forms
from .models import Client, HistoriqueVisite
from django.core.exceptions import ValidationError
import re

class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = '__all__'
        exclude = ['code', 'date_premiere_visite', 'date_derniere_visite', 'points_fidelite']
        widgets = {
            'date_naissance': forms.DateInput(attrs={'type': 'date'}),
            'adresse': forms.Textarea(attrs={'rows': 3}),
            'allergies': forms.Textarea(attrs={'rows': 2}),
            'preferences': forms.Textarea(attrs={'rows': 2}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }
    
    def clean_telephone(self):
        telephone = self.cleaned_data['telephone']
        # Nettoyer le numéro
        telephone = re.sub(r'[^\d\+]', '', telephone)
        if len(telephone) < 8:
            raise ValidationError("Numéro de téléphone trop court")
        return telephone

class HistoriqueVisiteForm(forms.ModelForm):
    class Meta:
        model = HistoriqueVisite
        fields = ['date_visite', 'employe', 'service', 'montant', 'satisfaction', 'commentaire']
        widgets = {
            'date_visite': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'commentaire': forms.Textarea(attrs={'rows': 3}),
        }