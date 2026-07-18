from django import forms
from django.utils import timezone
from datetime import timedelta
#from .models import RendezVous, BlocageHoraire
from employes.models import Employe

from datetime import timedelta
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
#from .models import RendezVous

'''
class RendezVousForm(forms.ModelForm):
    

    class Meta:
        model = RendezVous
        exclude = [
            'code',
            'duree_estimee',
            'montant',
            'commission',
            'statut',
            'created_at',
            'updated_at',
        ]
        #fields = '__all__'  # ou une liste précise
        widgets = {
            'date_heure': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        date_heure = cleaned_data.get('date_heure')
        service = cleaned_data.get('service')
        employe = cleaned_data.get('employe')

        if not date_heure  or not employe:
            return cleaned_data

        duree_estimee = service.duree

        heure_fin = date_heure + timedelta(minutes=duree_estimee)

        # 🔥 ON NE FILTRE QUE SUR DES CHAMPS RÉELS
        rdvs = RendezVous.objects.filter(
            employe=employe,
            date_heure__lt=heure_fin,
        )

        # Exclure soi-même en cas de modification
        if self.instance.pk:
            rdvs = rdvs.exclude(pk=self.instance.pk)

        # Vérification en PYTHON (pas SQL)
        for rdv in rdvs:
            if rdv.heure_fin_estimee > date_heure:
                raise ValidationError(
                    "Ce créneau est déjà occupé pour cet employé."
                )

        return cleaned_data


class BlocageHoraireForm(forms.ModelForm):
    class Meta:
        model = BlocageHoraire
        fields = ['employe', 'date_debut', 'date_fin', 'motif', 'notes']
        widgets = {
            'date_debut': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'date_fin': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }

class RendezVousStatutForm(forms.ModelForm):
    class Meta:
        model = RendezVous
        fields = ['statut', 'duree_reelle', 'notes_client', 'satisfaction']
        widgets = {
            'notes_client': forms.Textarea(attrs={'rows': 3}),
        }








from django import forms
from django.utils import timezone
from django.db.models import Sum

from .models import PaiementEmploye
from employes.models import Employe
from gestion.models import Service


from django import forms
from .models import PaiementEmploye



class PaiementEmployeForm(forms.ModelForm):

    class Meta:
        model = PaiementEmploye

        fields = [
            "employe",
            "services",
            "date_paiement",
        ]

        widgets = {

            "employe": forms.Select(
                attrs={
                    "class": "form-control"
                }
            ),

            "services": forms.CheckboxSelectMultiple(
                attrs={
                    "class": "form-check-input"
                }
            ),

            "date_paiement": forms.DateTimeInput(
                attrs={
                    "type": "datetime-local",
                    "class": "form-control"
                }
            ),
        }

        labels = {

            "employe": "Employé",

            "services": "Services effectués",

            "date_paiement": "Date du paiement",
        }
        '''









from django import forms
from django.utils import timezone
from django.db.models import Sum

from .models import PaiementEmploye
from employes.models import Employe
from gestion.models import Service

from django import forms
from .models import PaiementEmploye

class PaiementEmployeForm(forms.ModelForm):

    class Meta:
        model = PaiementEmploye
        fields = [
            "employe",
            "services",
            "date_paiement",
        ]

        widgets = {

            "employe": forms.Select(
                attrs={
                    "class": "form-select"
                }
            ),

            "services": forms.CheckboxSelectMultiple(
                attrs={
                    "class": "form-check-input"
                }
            ),

            "date_paiement": forms.DateTimeInput(
                attrs={
                    "type": "datetime-local",
                    "class": "form-control"
                }
            ),
        }

        labels = {
            "employe": "Employé",
            "services": "Services effectués",
            "date_paiement": "Date du paiement",
        }

    def clean_services(self):
        services = self.cleaned_data.get("services")

        if not services:
            raise forms.ValidationError("Veuillez sélectionner au moins un service.")

        return services