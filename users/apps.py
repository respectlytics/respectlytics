from django.apps import AppConfig


class UsersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "users"

    def ready(self):
        """Import signals when the app is ready."""
        from django.apps import apps

        import users.signals  # noqa: F401

        # respectlytics.com's sign-in lockout (users/lockout.py). The community edition has no
        # axes and keeps its own lockout.
        if apps.is_installed("axes"):
            from axes.signals import user_locked_out
            from django.contrib.auth.signals import user_logged_in, user_login_failed

            from . import lockout

            user_login_failed.connect(
                lockout.warn_after_failures, dispatch_uid="users.lockout.warn"
            )
            user_locked_out.connect(lockout.alert_on_lockout, dispatch_uid="users.lockout.alert")
            user_logged_in.connect(lockout.forget_success, dispatch_uid="users.lockout.success")
