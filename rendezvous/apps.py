from django.apps import AppConfig


class rendezvousConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'rendezvous'
    verbose_name = 'Gestion des Rendez-Vous'

    def ready(self):
        import rendezvous.signals
        import inventaire.signals