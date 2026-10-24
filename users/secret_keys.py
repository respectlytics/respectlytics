"""The account's secret keys for the API (analytics.models.SecretKey), made, listed and
revoked on the account page, in both editions. A new key is shown once, in the answer to the
request that made it, and kept nowhere: only its digest is stored."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from analytics.models import SecretKey


@never_cache
@login_required
def account_api_keys_view(request):
    keys = SecretKey.objects.filter(user=request.user)
    new_key = None
    if request.method == "POST":
        if keys.count() >= SecretKey.LIMIT:
            messages.error(request, f"You have {SecretKey.LIMIT} keys. Revoke one first.")
            return redirect("account_api_keys")
        _, new_key = SecretKey.make(request.user)
    app = request.user.apps.order_by("created_at").first()
    return render(
        request,
        "users/account/api_keys.html",
        {
            "active_tab": "api_keys",
            "keys": keys,
            "new_key": new_key,
            "at_limit": new_key is None and keys.count() >= SecretKey.LIMIT,
            "limit": SecretKey.LIMIT,
            "example_url": request.build_absolute_uri(reverse("analytics:event-summary")),
            "example_secret": new_key or "YOUR_SECRET_KEY",
            "example_app_key": str(app.id) if app else "YOUR_APP_KEY",
        },
    )


@require_POST
@login_required
def account_api_key_revoke_view(request, pk):
    deleted, _ = SecretKey.objects.filter(pk=pk, user=request.user).delete()
    if deleted:
        messages.success(request, "Key revoked. Requests with it are refused from now on.")
    return redirect("account_api_keys")
