from django.apps import AppConfig


class AnalyticsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "analytics"

    def ready(self):
        from django.contrib.auth.signals import user_login_failed

        from .blocks import block_attack_login

        user_login_failed.connect(block_attack_login, dispatch_uid="analytics.blocks.login")
