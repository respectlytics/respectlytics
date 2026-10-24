from django.contrib.auth.models import User
from django.db import models


class UserPreferences(models.Model):
    """
    User email notification preferences.

    PROF-009: Allows users to control which non-transactional emails they receive.

    Email Categories:
    - Transactional: Always sent (payments, password resets, security alerts)
    - Important Updates: usage warnings and notices about the account (default ON)
    - Product News: New features, tips, re-engagement (default OFF - opt-in)
    """

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="preferences")

    # Important Updates: usage warnings and notices about the account (default ON)
    email_important_updates = models.BooleanField(
        default=True, help_text="Receive usage warnings and notices about the account"
    )

    # Product News: new features, tips, re-engagement (default OFF - opt-in)
    email_product_news = models.BooleanField(
        default=False, help_text="Receive product updates, tips, and feature announcements"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User preferences"
        verbose_name_plural = "User preferences"

    def __str__(self):
        return f"Preferences for {self.user.email}"
