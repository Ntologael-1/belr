from django.core.management.base import BaseCommand
from clients.models import Client
import random
import string
from datetime import date, timedelta


def generate_unique_code(prefix="CL"):
    """Génère un code client unique"""
    return prefix + "".join(random.choices(string.digits, k=6))


class Command(BaseCommand):
    help = "Génère des clients fictifs"

    def handle(self, *args, **kwargs):

        prenoms = ["Paul", "Emma", "Lucas", "Sarah", "Yanis", "Inès", "Adam", "Lina"]
        noms = ["Dupont", "Martin", "Durand", "Bernard", "Diallo", "Benali"]

        created_count = 0

        for i in range(30):
            code = generate_unique_code()

            # Sécurité : éviter toute collision
            while Client.objects.filter(code=code).exists():
                code = generate_unique_code()

            Client.objects.create(
                code=code,
                prenom=random.choice(prenoms),
                nom=random.choice(noms),
                telephone=f"060000{i:04}",
                email=f"client{i}@test.com",
                date_premiere_visite=date.today() - timedelta(days=random.randint(0, 365)),
            )

            created_count += 1

        self.stdout.write(
            self.style.SUCCESS(f"✔ {created_count} clients fictifs créés")
        )
