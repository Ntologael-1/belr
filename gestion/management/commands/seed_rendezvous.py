from django.core.management.base import BaseCommand
from django.utils import timezone
from rendezvous.models import RendezVous
from employes.models import Employe
from gestion.models import Service
from clients.models import Client
from datetime import timedelta
import random
from decimal import Decimal



class Command(BaseCommand):
    help = "Génère des rendez-vous fictifs réalistes"

    def handle(self, *args, **kwargs):

        employes = list(Employe.objects.all())
        services = list(Service.objects.all())
        clients = list(Client.objects.all())

        if not employes or not services or not clients:
            self.stdout.write(self.style.ERROR(
                "❌ Employés / Services / Clients manquants"
            ))
            return

        nb_rdv = 50
        created = 0

        for _ in range(nb_rdv):
            employe = random.choice(employes)
            service = random.choice(services)
            client = random.choice(clients)

            # Date aléatoire (30 derniers jours)
            date_heure = timezone.now() - timedelta(
                days=random.randint(0, 30),
                hours=random.randint(8, 18)
            )

            duree_estimee = service.duree
            duree_reelle = max(
                10,
                duree_estimee + random.randint(-5, 15)
            )

            montant = service.prix
            commission = montant * (Decimal(employe.taux_commission) / Decimal("100"))


            RendezVous.objects.create(
                code=f"RDV-{random.randint(100000, 999999)}",
                client=client,
                employe=employe,
                service=service,
                date_heure=date_heure,
                duree_estimee=duree_estimee,
                duree_reelle=duree_reelle,
                statut=random.choice(["termine", "annule", "planifie"]),
                montant=montant,
                commission=commission,
                satisfaction=random.randint(3, 5),
                rappel_envoye=random.choice([True, False]),
            )

            created += 1

        self.stdout.write(self.style.SUCCESS(
            f"✔ {created} rendez-vous générés avec succès"
        ))
