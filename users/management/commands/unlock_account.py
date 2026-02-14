"""
Management command to unlock a user account that was locked due to failed login attempts.

Usage:
    python manage.py unlock_account user@example.com
    python manage.py unlock_account --all  # Unlock all accounts (clears all lockouts)
"""
from django.core.management.base import BaseCommand, CommandError
from django.core.cache import cache


class Command(BaseCommand):
    help = 'Unlock a user account locked due to failed login attempts (SEC-003)'

    def add_arguments(self, parser):
        parser.add_argument(
            'email',
            nargs='?',
            type=str,
            help='Email address of the account to unlock'
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Clear all account lockouts (use with caution)'
        )

    def handle(self, *args, **options):
        if options['all']:
            # This is a simplified approach - in production you might want
            # to iterate through known locked accounts
            self.stdout.write(
                self.style.WARNING('Cannot clear all lockouts without iterating cache keys.')
            )
            self.stdout.write(
                'Please specify individual email addresses to unlock.'
            )
            return

        email = options.get('email')
        if not email:
            raise CommandError('Please provide an email address or use --all')

        email_lower = email.lower()
        
        # Check current status
        is_locked = cache.get(f'account_locked:{email_lower}', False)
        failed_attempts = cache.get(f'login_failures:{email_lower}', 0)
        
        if not is_locked and failed_attempts == 0:
            self.stdout.write(
                self.style.WARNING(f'Account {email} is not locked and has no failed attempts.')
            )
            return

        # Clear the lockout and failed attempts
        cache.delete(f'account_locked:{email_lower}')
        cache.delete(f'login_failures:{email_lower}')

        self.stdout.write(
            self.style.SUCCESS(f'Successfully unlocked account: {email}')
        )
        if failed_attempts > 0:
            self.stdout.write(f'  - Cleared {failed_attempts} failed login attempt(s)')
        if is_locked:
            self.stdout.write(f'  - Removed account lockout')