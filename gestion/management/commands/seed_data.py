from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from gestion.models import Service
from employes.models import Employe
from datetime import time, date, timedelta
import random
import string


def generate_unique_matricule():
    """Génère un matricule unique EMP-XXXX"""
    while True:
        matricule = "EMP-" + "".join(random.choices(string.digits, k=5))
        if not Employe.objects.filter(matricule=matricule).exists():
            return matricule


class Command(BaseCommand):
    help = "Insère des données fictives robustes pour tests"

    def handle(self, *args, **kwargs):

        # =====================
        # SERVICES
        # =====================
        services_data = [
            ("COUPE_H", "Coupe Homme", 15, 30, "#00D4AA"),
            ("COUPE_F", "Coupe Femme", 25, 45, "#FF6B8B"),
            ("COLOR", "Coloration", 45, 90, "#8A2BE2"),
            ("BRUSH", "Brushing", 20, 30, "#FF9F43"),
            ("BARBE", "Barbe", 12, 20, "#1E1E2E"),
            ("SOIN", "Soin capillaire", 18, 30, "#28C76F"),
        ]

        for code, nom, prix, duree, couleur in services_data:
            Service.objects.get_or_create(
                code=code,
                defaults={
                    "nom": nom,
                    "prix": prix,
                    "duree": duree,
                    "couleur": couleur,
                    "actif": True,
                }
            )

        self.stdout.write(self.style.SUCCESS("✔ Services OK"))

        # =====================
        # COIFFEURS
        # =====================
        employes_data = [
            ("julien", "Martin", "Julien", 50),
            ("aicha", "Diallo", "Aïcha", 55),
            ("sophie", "Dupont", "Sophie", 50),
            ("karim", "Benali", "Karim", 45),
            ("camille", "Leroy", "Camille", 50),
        ]

        for username, nom, prenom, commission in employes_data:

            user, _ = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": prenom,
                    "last_name": nom,
                }
            )

            if not user.has_usable_password():
                user.set_password("password123")
                user.save()

            Employe.objects.get_or_create(
                user=user,
                defaults={
                    "matricule": generate_unique_matricule(),
                    "taux_commission": commission,
                    "heure_debut": time(9, 0),
                    "heure_fin": time(18, 0),
                    "jours_travail": [
                        "Lundi", "Mardi", "Mercredi",
                        "Jeudi", "Vendredi", "Samedi"
                    ],
                    "date_embauche": date.today() - timedelta(days=random.randint(30, 1200)),
                    "actif": True
                }
            )

        self.stdout.write(self.style.SUCCESS("✔ Coiffeurs OK"))
        self.stdout.write(self.style.SUCCESS("🎉 Script exécuté sans collision"))
