"""
User signals for PROF-009: Email Notification Preferences.

Creates UserPreferences automatically when a new user is created.
"""

from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import Signal, receiver

from .models import UserPreferences

# Sent after a person's password was reset or changed, with `user`: whatever else proves who they
# are and was made before ends with it. A hook for any app installed beside this one.
password_renewed = Signal()


@receiver(post_save, sender=User)
def create_user_preferences(sender, instance, created, **kwargs):
    """
    Create UserPreferences when a new user is created.

    Default preferences:
    - email_important_updates = True (usage warnings and notices about the account)
    - email_product_news = False (user must opt-in during registration)
    """
    if created:
        UserPreferences.objects.get_or_create(user=instance)
