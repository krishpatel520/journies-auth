from django.apps import AppConfig


class AuthAppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'auth_app'

    def ready(self):
        """
        Wire up signals after the app registry is fully loaded.
        This fires the Tenant and UserModel → rbac DB sync on every save.
        """
        from auth_app.signals import register_signals
        register_signals()
