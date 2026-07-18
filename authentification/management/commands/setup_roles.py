# mon_application/management/commands/setup_roles.py
from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

class Command(BaseCommand):
    help = "Initialise les groupes et les permissions pour le salon BEL'R"

    def handle(self, *args, **options):
        # 1. Définition des rôles du SaaS
        roles = {
            'Gérant': {
                'description': "Accès total aux finances, statistiques et configuration",
                'permissions': ['view_dashboard', 'manage_salaires', 'manage_stocks']
            },
            'Manager': {
                'description': "Gestion quotidienne des rendez-vous et stocks cabine",
                'permissions': ['view_dashboard', 'manage_stocks']
            },
            'Employé': {
                'description': "Consultation de son propre planning et de ses commissions",
                'permissions': ['view_own_planning']
            }
        }

        # On utilise un ContentType fictif pour nos permissions d'application personnalisées
        content_type, _ = ContentType.objects.get_or_create(app_label='mon_application', model='bi_dashboard')

        for role_name, role_data in roles.items():
            # Création ou récupération du groupe
            group, created = Group.objects.get_or_create(name=role_name)
            if created:
                self.stdout.write(self.style.SUCCESS(f"Groupe '{role_name}' créé."))

            # Création et assignation des permissions
            group.permissions.clear()
            for perm_codename in role_data['permissions']:
                # Créer la permission si elle n'existe pas
                permission, _ = Permission.objects.get_or_create(
                    codename=perm_codename,
                    name=f"Can {perm_codename.replace('_', ' ')}",
                    content_type=content_type
                )
                group.permissions.add(permission)
                
        self.stdout.write(self.style.SUCCESS("Configuration des rôles terminée avec succès !"))