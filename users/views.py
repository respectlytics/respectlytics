"""
User authentication views — Community Edition

Stripped of:
- stripe import and Stripe subscription cancellation
- account_billing_view (no billing tab)
- DeletedUser archival in delete_account_view
- Redirect to 'website:home' replaced with redirect to 'login'
"""
import logging

from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sites.shortcuts import get_current_site
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.core.mail import EmailMultiAlternatives
from django.contrib import messages
from django.contrib.auth.models import User
from django.conf import settings
from django.core.cache import cache

# SEC-002: Rate limiting imports
from django_ratelimit.decorators import ratelimit

from .forms import RegistrationForm, LoginForm

# SEC-007: Security alert emails
from .security_emails import (
    send_account_lockout_alert,
    send_password_changed_notification,
    send_failed_login_warning
)

# SEC-010: Structured security event logger
from analytics.security_logger import log_security_event, SecurityEvent, get_client_info

# Security logger (for non-structured logs)
logger = logging.getLogger('analytics')


# SEC-007: Warning threshold (send email before lockout)
WARNING_THRESHOLD = 3  # Send warning email at 3 failed attempts

# =============================================================================
# SEC-003: Account Lockout Configuration
# =============================================================================
LOCKOUT_THRESHOLD = 5      # Lock after 5 failed attempts
LOCKOUT_DURATION = 1800    # 30 minutes lockout
ATTEMPT_WINDOW = 3600      # Count attempts within 1 hour window


def track_failed_login(email, ip_address=None):
    """
    Track failed login attempt and return lockout status.
    """
    email_lower = email.lower()
    cache_key = f'login_failures:{email_lower}'
    attempts = cache.get(cache_key, 0) + 1
    cache.set(cache_key, attempts, ATTEMPT_WINDOW)

    if attempts == WARNING_THRESHOLD:
        try:
            user = User.objects.filter(email__iexact=email_lower).first()
            if user:
                send_failed_login_warning(user, attempts, ip_address or 'Unknown')
                logger.info(f'[SECURITY_EMAIL] Sent warning to {email_lower} after {attempts} failed attempts')
        except Exception as e:
            logger.error(f'[SECURITY_EMAIL] Failed to send warning email: {e}')

    if attempts >= LOCKOUT_THRESHOLD:
        cache.set(f'account_locked:{email_lower}', True, LOCKOUT_DURATION)
        logger.warning(f'[SECURITY] Account locked after {attempts} failed attempts: {email_lower}')

        try:
            send_account_lockout_alert(email_lower, ip_address or 'Unknown', attempts)
            logger.info(f'[SECURITY_EMAIL] Sent lockout alert to admin for {email_lower}')
        except Exception as e:
            logger.error(f'[SECURITY_EMAIL] Failed to send lockout alert: {e}')

        return True

    logger.info(f'[SECURITY] Failed login attempt #{attempts} for: {email_lower}')
    return False


def is_account_locked(email):
    """Check if account is locked due to failed attempts."""
    if not email:
        return False
    return cache.get(f'account_locked:{email.lower()}', False)


def clear_failed_attempts(email):
    """Clear failed attempts after successful login."""
    email_lower = email.lower()
    cache.delete(f'login_failures:{email_lower}')
    cache.delete(f'account_locked:{email_lower}')


def get_failed_attempts(email):
    """Get current number of failed attempts for an email."""
    if not email:
        return 0
    return cache.get(f'login_failures:{email.lower()}', 0)


def unlock_account(email):
    """Manually unlock an account (for admin use)."""
    email_lower = email.lower()
    cache.delete(f'login_failures:{email_lower}')
    cache.delete(f'account_locked:{email_lower}')
    logger.info(f'[SECURITY] Account manually unlocked: {email_lower}')
    return True


def register_view(request):
    """
    User registration with email verification.
    """
    if request.user.is_authenticated:
        return redirect('dashboard:main')

    registration_closed = getattr(settings, 'REGISTRATION_CLOSED', False)
    if registration_closed:
        return render(request, 'users/auth/register.html', {
            'registration_closed': True
        })

    client_ip = _get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', '')

    if request.method == 'POST':
        from django_ratelimit.core import is_ratelimited

        rate_limited = is_ratelimited(
            request=request,
            group='register',
            key='ip',
            rate='5/h',
            method='POST',
            increment=True
        )

        if rate_limited:
            log_security_event(
                SecurityEvent.RATE_LIMITED,
                ip=client_ip,
                user_agent=user_agent,
                reason='Registration rate limit exceeded',
                path='/register/',
                severity='WARNING'
            )
            messages.error(request, 'Too many registration attempts. Please try again in an hour.')
            return render(request, 'users/auth/register.html', {
                'form': RegistrationForm(),
                'rate_limited': True
            })

    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()

            log_security_event(
                SecurityEvent.REGISTRATION_STARTED,
                ip=client_ip,
                email=user.email,
                user_id=user.id,
                user_agent=user_agent
            )

            # NOTE: email_product_news preference removed in Community Edition

            current_site = get_current_site(request)
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))

            protocol = 'https' if getattr(settings, 'SECURE_SSL', False) else 'http'
            verification_link = f"{protocol}://{current_site.domain}/verify-email/{uid}/{token}/"

            subject = 'Verify your Respectlytics account'
            message = f"""
Welcome to Respectlytics!

Please verify your email address by clicking the link below:

{verification_link}

This link will expire in 24 hours.

If you didn't create this account, please ignore this email.

Best regards,
The Respectlytics Team
            """

            email = EmailMultiAlternatives(
                subject=subject,
                body=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[user.email],
                reply_to=[settings.EMAIL_REPLY_TO],
            )
            email.send(fail_silently=False)

            return redirect('registration_complete')
    else:
        form = RegistrationForm()

    return render(request, 'users/auth/register.html', {'form': form})


def verify_email(request, uidb64, token):
    """Email verification handler."""
    client_ip = _get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', '')

    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user and default_token_generator.check_token(user, token):
        user.is_active = True
        user.save()

        log_security_event(
            SecurityEvent.EMAIL_VERIFIED,
            ip=client_ip,
            email=user.email,
            user_id=user.id,
            user_agent=user_agent
        )

        messages.success(request, 'Email verified! You can now log in.')
        return redirect('login')
    else:
        messages.error(request, 'Verification link is invalid or has expired.')
        return redirect('register')


def login_view(request):
    """User login with rate limiting and account lockout."""
    if request.user.is_authenticated:
        return redirect('dashboard:main')

    username = request.POST.get('username', '').lower() if request.method == 'POST' else ''
    client_ip = _get_client_ip(request)
    user_agent = request.META.get('HTTP_USER_AGENT', '')

    if request.method == 'POST' and username and is_account_locked(username):
        log_security_event(
            SecurityEvent.LOGIN_FAILURE,
            ip=client_ip,
            email=username,
            user_agent=user_agent,
            reason='Account locked',
            severity='WARNING'
        )
        messages.error(request, 'Account temporarily locked due to too many failed attempts. Please try again in 30 minutes or reset your password.')
        return render(request, 'users/auth/login.html', {
            'form': LoginForm(),
            'account_locked': True
        })

    rate_limited = False
    if request.method == 'POST':
        from django_ratelimit.core import is_ratelimited

        ip_limited = is_ratelimited(
            request=request,
            group='login',
            key='ip',
            rate='5/10m',
            method='POST',
            increment=True
        )

        user_limited = False
        if username:
            user_limited = is_ratelimited(
                request=request,
                group='login_user',
                key=lambda g, r: username,
                rate='5/10m',
                method='POST',
                increment=True
            )

        rate_limited = ip_limited or user_limited

        if rate_limited:
            log_security_event(
                SecurityEvent.RATE_LIMITED,
                ip=client_ip,
                email=username,
                user_agent=user_agent,
                reason='Login rate limit exceeded',
                limit_type='ip' if ip_limited else 'username',
                severity='WARNING'
            )
            messages.error(request, 'Too many login attempts. Please wait 10 minutes and try again.')
            return render(request, 'users/auth/login.html', {
                'form': LoginForm(),
                'rate_limited': True
            })

    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            email = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(username=email, password=password)
            if user is not None:
                clear_failed_attempts(email)
                login(request, user)
                log_security_event(
                    SecurityEvent.LOGIN_SUCCESS,
                    ip=client_ip,
                    email=email,
                    user_id=user.id,
                    user_agent=user_agent
                )
                next_url = request.GET.get('next', 'dashboard:main')
                return redirect(next_url)
        else:
            email = request.POST.get('username', '')
            if email:
                is_now_locked = track_failed_login(email, ip_address=client_ip)
                log_security_event(
                    SecurityEvent.LOGIN_FAILURE,
                    ip=client_ip,
                    email=email,
                    user_agent=user_agent,
                    reason='Invalid credentials',
                    severity='WARNING'
                )
                if is_now_locked:
                    messages.error(request, 'Account locked due to too many failed attempts. Please try again in 30 minutes or reset your password.')
                    return render(request, 'users/auth/login.html', {
                        'form': LoginForm(),
                        'account_locked': True
                    })
            messages.error(request, 'Invalid email or password.')
    else:
        form = LoginForm()

    return render(request, 'users/auth/login.html', {'form': form})


def _get_client_ip(request):
    """Get client IP address, considering proxies."""
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    return ip


@login_required
def logout_view(request):
    """User logout — Community Edition redirects to login page."""
    logout(request)
    messages.success(request, 'You have been logged out.')
    return redirect('login')


def registration_complete_view(request):
    """Page shown after successful registration."""
    return render(request, 'users/auth/registration_complete.html')


@ratelimit(key='ip', rate='3/h', method='POST', block=False)
@ratelimit(key='post:email', rate='3/h', method='POST', block=False)
def resend_verification_email(request):
    """Resend verification email to user."""
    if request.method != 'POST':
        return redirect('register')

    was_limited = getattr(request, 'limited', False)
    if was_limited:
        messages.error(request, 'Too many resend attempts. Please wait an hour before trying again.')
        return redirect('registration_complete')

    email = request.POST.get('email', '').strip()

    if not email:
        messages.error(request, 'Please provide your email address.')
        return redirect('registration_complete')

    try:
        user = User.objects.get(email=email, is_active=False)

        current_site = get_current_site(request)
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))

        protocol = 'https' if getattr(settings, 'SECURE_SSL', False) else 'http'
        verification_link = f"{protocol}://{current_site.domain}/verify-email/{uid}/{token}/"

        subject = 'Verify your Respectlytics account'
        message = f"""
Welcome to Respectlytics!

Please verify your email address by clicking the link below:

{verification_link}

This link will expire in 24 hours.

If you didn't create this account, please ignore this email.

Best regards,
The Respectlytics Team
        """

        email_msg = EmailMultiAlternatives(
            subject=subject,
            body=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
            reply_to=[settings.EMAIL_REPLY_TO],
        )
        email_msg.send(fail_silently=False)

        messages.success(request, f'Verification email has been resent to {user.email}. Please check your inbox.')
    except User.DoesNotExist:
        messages.success(request, f'If an unverified account exists with {email}, a verification email has been sent.')
    except Exception as e:
        messages.error(request, 'An error occurred while sending the email. Please try again later.')

    return redirect('registration_complete')


# =============================================================================
# PROF-001: Account Settings Views
# =============================================================================

@login_required
def account_view(request):
    """Main account settings page - redirects to profile tab."""
    return redirect('account_profile')


@login_required
def account_profile_view(request):
    """Account profile tab with email update functionality."""
    from .forms import EmailUpdateForm

    if request.method == 'POST':
        form = EmailUpdateForm(request.POST, user=request.user)
        if form.is_valid():
            request.user.email = form.cleaned_data['email']
            request.user.username = form.cleaned_data['email']
            request.user.save()
            messages.success(request, 'Your email address has been updated successfully.')
            return redirect('account_profile')
    else:
        form = EmailUpdateForm(initial={'email': request.user.email}, user=request.user)

    return render(request, 'users/account/profile.html', {
        'active_tab': 'profile',
        'email_form': form
    })


# NOTE: account_billing_view removed in Community Edition (no billing)
# NOTE: account_preferences_view removed in Community Edition (no email marketing/quota notifications)


@login_required
def account_security_view(request):
    """Account security tab with password change functionality."""
    from django.contrib.auth import update_session_auth_hash
    from .forms import PasswordChangeForm

    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            update_session_auth_hash(request, user)
            messages.success(request, 'Your password was successfully updated!')

            try:
                send_password_changed_notification(user)
                logger.info(f'[SECURITY_EMAIL] Sent password changed notification to {user.email}')
            except Exception as e:
                logger.error(f'[SECURITY_EMAIL] Failed to send password changed notification: {e}')

            return redirect('account_security')
    else:
        form = PasswordChangeForm(request.user)

    return render(request, 'users/account/security.html', {
        'active_tab': 'security',
        'form': form
    })


# DATA-001: Data Management tab
@login_required
def account_data_management_view(request):
    """Account data management tab."""
    from analytics.models import DeletionLog
    from django.db.models import Sum

    logs = (
        DeletionLog.objects
        .filter(deleted_by=request.user)
        .order_by('-deleted_at')[:50]
    )

    total_deleted = (
        DeletionLog.objects
        .filter(deleted_by=request.user)
        .aggregate(total=Sum('events_deleted'))
    )['total'] or 0

    deletion_count = DeletionLog.objects.filter(deleted_by=request.user).count()

    return render(request, 'users/account/data_management.html', {
        'active_tab': 'data_management',
        'logs': logs,
        'total_deleted': total_deleted,
        'deletion_count': deletion_count,
    })


# =============================================================================
# PROF-011: Account Deletion — Community Edition
# =============================================================================


@login_required
def delete_account_view(request):
    """
    Delete user account — Community Edition.

    Simplified:
    - No Stripe subscription cancellation
    - No DeletedUser archival
    - Deletes all apps (cascade to events) and user account
    """
    from .forms import DeleteAccountForm

    user = request.user

    if request.method == 'POST':
        form = DeleteAccountForm(user, request.POST)
        if form.is_valid():
            email = user.email

            # Delete apps (cascades to events)
            app_count = user.apps.count()
            user.apps.all().delete()
            logger.info(f'[ACCOUNT_DELETE] Deleted {app_count} apps for {email}')

            # Delete user
            user.delete()
            logger.info(f'[ACCOUNT_DELETE] Deleted user account for {email}')

            # Logout and redirect
            logout(request)
            messages.success(request, 'Your account has been permanently deleted. You can create a new account anytime.')
            return redirect('register')
    else:
        form = DeleteAccountForm(user)

    return render(request, 'users/account/delete_confirm.html', {
        'form': form,
        'has_active_subscription': False,
        'plan_name': None,
    })


# =============================================================================
# Password Reset Views
# =============================================================================

from django.contrib.auth import views as auth_views
from django.contrib.auth.forms import PasswordResetForm
from django.template.loader import render_to_string


class CustomPasswordResetForm(PasswordResetForm):
    """Custom password reset form that allows inactive users to reset their password."""

    def get_users(self, email):
        from django.contrib.auth import get_user_model
        UserModel = get_user_model()

        active_users = UserModel._default_manager.filter(
            **{
                f'{UserModel.get_email_field_name()}__iexact': email,
            }
        )
        return (
            u for u in active_users
            if u.has_usable_password()
        )


class CustomPasswordResetView(auth_views.PasswordResetView):
    """Custom password reset view with reply-to header and rate limiting."""

    form_class = CustomPasswordResetForm

    def post(self, request, *args, **kwargs):
        from django_ratelimit.core import is_ratelimited

        ip_limited = is_ratelimited(
            request=request,
            group='password_reset',
            key='ip',
            rate='3/h',
            method='POST',
            increment=True
        )

        email = request.POST.get('email', '').lower()
        email_limited = False
        if email:
            email_limited = is_ratelimited(
                request=request,
                group='password_reset_email',
                key=lambda g, r: email,
                rate='3/h',
                method='POST',
                increment=True
            )

        if ip_limited or email_limited:
            x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
            if x_forwarded_for:
                client_ip = x_forwarded_for.split(',')[0]
            else:
                client_ip = request.META.get('REMOTE_ADDR')

            logger.warning(f'[SECURITY] Password reset rate limited - IP: {client_ip}, email: {email}')
            messages.error(request, 'Too many password reset requests. Please try again in an hour.')
            return render(request, 'users/auth/password_reset.html', {
                'form': self.get_form(),
                'rate_limited': True
            })

        return super().post(request, *args, **kwargs)

    def send_mail(self, subject_template_name, email_template_name,
                  context, from_email, to_email, html_email_template_name=None):
        subject = render_to_string(subject_template_name, context).strip()
        body = render_to_string(email_template_name, context)

        email = EmailMultiAlternatives(
            subject=subject,
            body=body,
            from_email=from_email,
            to=[to_email],
            reply_to=[settings.EMAIL_REPLY_TO],
        )

        if html_email_template_name:
            html_body = render_to_string(html_email_template_name, context)
            email.attach_alternative(html_body, 'text/html')

        email.send(fail_silently=False)


class CustomPasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    """Custom password reset confirm view that clears failed login attempts."""

    def form_valid(self, form):
        response = super().form_valid(form)

        user = form.user
        if user:
            if user.email:
                clear_failed_attempts(user.email)
                logger.info(f'[SECURITY] Cleared failed login attempts after password reset: {user.email}')

            if not user.is_active:
                user.is_active = True
                user.save()
                logger.info(f'[SECURITY] Activated inactive account via password reset: {user.email}')

        return response
