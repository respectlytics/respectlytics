from django.db import models
from django.contrib.auth.models import User


class UserPreferences(models.Model):
    """
    User email notification preferences.
    
    PROF-009: Allows users to control which non-transactional emails they receive.
    
    Email Categories:
    - Transactional: Always sent (payments, password resets, security alerts)
    - Important Updates: Quota warnings, trial expiry (default ON)
    - Product News: New features, tips, re-engagement (default OFF - opt-in)
    """
    user = models.OneToOneField(
        User, 
        on_delete=models.CASCADE, 
        related_name='preferences'
    )
    
    # Important Updates: quota warnings, trial expiry (default ON)
    email_important_updates = models.BooleanField(
        default=True, 
        help_text="Receive quota warnings and trial expiry notifications"
    )
    
    # Product News: new features, tips, re-engagement (default OFF - opt-in)
    email_product_news = models.BooleanField(
        default=False, 
        help_text="Receive product updates, tips, and feature announcements"
    )
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "User preferences"
        verbose_name_plural = "User preferences"
    
    def __str__(self):
        return f"Preferences for {self.user.email}"
