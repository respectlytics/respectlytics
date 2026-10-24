from django import forms
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth.forms import PasswordChangeForm as DjangoPasswordChangeForm
from django.contrib.auth.models import User


class RegistrationForm(UserCreationForm):
    """
    User registration form with email and password.

    SEC-004: Includes Cloudflare Turnstile CAPTCHA when configured.
    PROF-009: Includes optional opt-in for product news emails.
    """

    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "your@company.com",
                "autofocus": True,
            }
        ),
    )

    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Choose a strong password",
            }
        ),
        help_text="At least 8 characters",
    )

    password2 = forms.CharField(
        label="Confirm Password",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Confirm your password",
            }
        ),
    )

    # PROF-009: Product news opt-in (shown during registration)
    email_product_news = forms.BooleanField(
        required=False,
        label="Keep me updated about new features and tips",
        widget=forms.CheckboxInput(
            attrs={
                "class": (
                    "w-4 h-4 text-purple-600 bg-slate-700 border-slate-600 rounded "
                    "focus:ring-purple-500"
                )
            }
        ),
    )

    class Meta:
        model = User
        fields = ("email", "password1", "password2")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Remove username field - we'll use email
        if "username" in self.fields:
            del self.fields["username"]

        # SEC-004: Add Turnstile CAPTCHA field when configured
        if getattr(settings, "TURNSTILE_SITEKEY", ""):
            from turnstile.fields import TurnstileField

            self.fields["turnstile"] = TurnstileField(
                theme="dark",  # Match our dark theme
            )
            # Add callbacks for button enable/disable
            self.fields["turnstile"].widget.attrs.update(
                {
                    "data-callback": "onTurnstileSuccess",
                    "data-expired-callback": "onTurnstileExpire",
                    "data-error-callback": "onTurnstileError",
                }
            )

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("This email is already registered.")
        return email.lower()

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.username = self.cleaned_data["email"]  # Use email as username
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
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": "your@company.com",
                "autofocus": True,
            }
        ),
    )

    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Your password",
            }
        )
    )


class EmailUpdateForm(forms.Form):
    """Form for updating user email address."""

    # The account pages' one field look (.field); the label is in the template, so no placeholder
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={"class": "field", "autocomplete": "email"}),
    )

    # Asked with the password, so a session left open cannot hand the account to another
    # address; on respectlytics.com the change also waits for the new address to be confirmed
    password = forms.CharField(
        required=True,
        strip=False,
        widget=forms.PasswordInput(attrs={"class": "field", "autocomplete": "current-password"}),
    )

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").lower()
        if email and email == (self.user.email or "").lower():
            raise forms.ValidationError("That is already your address.")
        if email and User.objects.filter(email__iexact=email).exclude(pk=self.user.pk).exists():
            raise forms.ValidationError("This email is already in use by another account.")
        return email

    def clean_password(self):
        password = self.cleaned_data.get("password")
        if not self.user.check_password(password or ""):
            raise forms.ValidationError("That is not your current password.")
        return password


class PasswordChangeForm(DjangoPasswordChangeForm):
    """The password page's form, in the account pages' field look, with each field saying what
    it holds so a password manager fills it (WCAG 1.3.5)."""

    old_password = forms.CharField(
        label="Current password",
        widget=forms.PasswordInput(attrs={"class": "field", "autocomplete": "current-password"}),
    )
    new_password1 = forms.CharField(
        label="New password",
        widget=forms.PasswordInput(
            attrs={
                "class": "field",
                "autocomplete": "new-password",
                "aria-describedby": "newPasswordHint",
            }
        ),
    )
    new_password2 = forms.CharField(
        label="New password again",
        widget=forms.PasswordInput(attrs={"class": "field", "autocomplete": "new-password"}),
    )


class DeleteAccountForm(forms.Form):
    """
    Form for account deletion with password confirmation.

    PROF-011: Requires password verification before account deletion
    to prevent accidental or unauthorized deletions.
    """

    password = forms.CharField(
        widget=forms.PasswordInput(attrs={"class": "field", "autocomplete": "current-password"}),
        label="Password",
    )

    def __init__(self, user, *args, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_password(self):
        password = self.cleaned_data.get("password")
        if not self.user.check_password(password):
            raise forms.ValidationError("Incorrect password.")
        return password
