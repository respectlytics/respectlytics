from django import forms
from django.conf import settings
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm, PasswordChangeForm as DjangoPasswordChangeForm
from django.contrib.auth.models import User


class RegistrationForm(UserCreationForm):
    """
    User registration form with email and password.
    
    SEC-004: Includes Cloudflare Turnstile CAPTCHA when configured.
    PROF-009: Includes optional opt-in for product news emails.
    """
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'your@company.com',
            'autofocus': True,
        })
    )
    
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Choose a strong password',
        }),
        help_text="At least 8 characters"
    )
    
    password2 = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm your password',
        })
    )
    
    # PROF-009: Product news opt-in (shown during registration)
    email_product_news = forms.BooleanField(
        required=False,
        label="Keep me updated about new features and tips",
        widget=forms.CheckboxInput(attrs={
            'class': 'w-4 h-4 text-purple-600 bg-slate-700 border-slate-600 rounded focus:ring-purple-500'
        })
    )

    class Meta:
        model = User
        fields = ('email', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Remove username field - we'll use email
        if 'username' in self.fields:
            del self.fields['username']
        
        # SEC-004: Add Turnstile CAPTCHA field when configured
        if getattr(settings, 'TURNSTILE_SITEKEY', ''):
            from turnstile.fields import TurnstileField
            self.fields['turnstile'] = TurnstileField(
                theme='dark',  # Match our dark theme
            )
            # Add callbacks for button enable/disable
            self.fields['turnstile'].widget.attrs.update({
                'data-callback': 'onTurnstileSuccess',
                'data-expired-callback': 'onTurnstileExpire',
                'data-error-callback': 'onTurnstileError',
            })

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("This email is already registered.")
        return email.lower()

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.username = self.cleaned_data['email']  # Use email as username
        user.is_active = False  # Require email verification
        if commit:
            user.save()
        return user


class LoginForm(AuthenticationForm):
    """
    Clean, modern login form.
    """
    username = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'your@company.com',
            'autofocus': True,
        })
    )
    
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Your password',
        })
    )


class EmailUpdateForm(forms.Form):
    """Form for updating user email address."""
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={
            'class': 'w-full px-4 py-3 bg-slate-800 border border-white/10 rounded-lg text-slate-50 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-purple-500',
            'placeholder': 'your@email.com'
        })
    )
    
    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email and User.objects.filter(email=email).exclude(pk=self.user.pk).exists():
            raise forms.ValidationError("This email is already in use by another account.")
        return email.lower()


class PasswordChangeForm(DjangoPasswordChangeForm):
    """Custom password change form with styled fields."""
    
    old_password = forms.CharField(
        label="Current Password",
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 bg-slate-800 border border-white/10 rounded-lg text-slate-50 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-purple-500',
            'placeholder': 'Current password'
        })
    )
    new_password1 = forms.CharField(
        label="New Password",
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 bg-slate-800 border border-white/10 rounded-lg text-slate-50 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-purple-500',
            'placeholder': 'New password'
        })
    )
    new_password2 = forms.CharField(
        label="Confirm New Password",
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 bg-slate-800 border border-white/10 rounded-lg text-slate-50 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-purple-500',
            'placeholder': 'Confirm new password'
        })
    )


class DeleteAccountForm(forms.Form):
    """
    Form for account deletion with password confirmation.
    
    PROF-011: Requires password verification before account deletion
    to prevent accidental or unauthorized deletions.
    """
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 bg-slate-700/50 border border-white/10 rounded-lg text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-red-500/50 focus:border-red-500/50',
            'placeholder': 'Enter your password to confirm',
        }),
        label='Password'
    )
    
    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
    
    def clean_password(self):
        password = self.cleaned_data.get('password')
        if not self.user.check_password(password):
            raise forms.ValidationError('Incorrect password.')
        return password
