"""
User signals for PROF-009: Email Notification Preferences.

Creates UserPreferences automatically when a new user is created.
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User

from .models import UserPreferences


@receiver(post_save, sender=User)
def create_user_preferences(sender, instance, created, **kwargs):
    """
    Create UserPreferences when a new user is created.
    
    Default preferences:
    - email_important_updates = True (user receives quota/trial warnings)
    - email_product_news = False (user must opt-in during registration)
    """
    if created:
        UserPreferences.objects.get_or_create(user=instance)
