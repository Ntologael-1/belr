from django import forms
from .models import Service, CategorieService, Salon, Parametre

from django import forms
from django.forms import CheckboxSelectMultiple
from .models import Service


class ServiceForm(forms.ModelForm):
    class Meta:
        model = Service
        fields = [
            'code',
            'nom',
            'categorie',
            'description',
            'duree',
            'couleur',
            'actif',
            'prix',
            'est_un_pack',
            'services_inclus',
        ]
        widgets = {
            'services_inclus': CheckboxSelectMultiple(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Afficher uniquement les services simples actifs
        self.fields['services_inclus'].queryset = Service.objects.filter(
            est_un_pack=False,
            actif=True
        ).order_by('nom')

        # Rendre le code optionnel dans le formulaire (si génération auto)
        self.fields['code'].required = False

        # Labels / aides (optionnel mais premium)
        self.fields['est_un_pack'].label = "Créer ce service comme un pack"
        self.fields['services_inclus'].label = "Sélectionnez les services à inclure"

    def clean(self):
        cleaned_data = super().clean()
        est_un_pack = cleaned_data.get('est_un_pack')
        services_inclus = cleaned_data.get('services_inclus')

        # Si l'utilisateur coche "pack", il doit choisir au moins un service
        if est_un_pack and (not services_inclus or services_inclus.count() == 0):
            self.add_error(
                'services_inclus',
                "Veuillez sélectionner au moins un service pour créer un pack."
            )

        # Si l'utilisateur ne coche PAS pack, on vide les services inclus
        # (sécurité métier)
        if not est_un_pack:
            cleaned_data['services_inclus'] = self.fields['services_inclus'].queryset.none()

        return cleaned_data



class CategorieServiceForm(forms.ModelForm):
    class Meta:
        model = CategorieService
        fields = '__all__'

class SalonForm(forms.ModelForm):
    class Meta:
        model = Salon
        fields = '__all__'
        widgets = {
            'adresse': forms.Textarea(attrs={'rows': 3}),
        }