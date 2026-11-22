from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "users"

    def ready(self):
        """Import signals when the app is ready."""
        from django.apps import apps

        import users.signals  # noqa: F401

        # The sign-in lockout built on django-axes, where it is installed. The community
        # edition has no axes and keeps its own lockout.
        if apps.is_installed("axes"):
            from axes.signals import user_locked_out

            from . import lockout

            user_locked_out.connect(lockout.alert_on_lockout, dispatch_uid="users.lockout.alert")
