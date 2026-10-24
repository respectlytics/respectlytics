"""What a refused form says, instead of Django's bare "CSRF verification failed" page.

A form is refused when the security token it carries no longer matches the browser's cookie:
the page was open from before the visitor signed in or out in another tab, the browser
restored an old copy, or cookies were cleared. Nothing is wrong and nothing was done. A sign-in,
sign-up or password reset page opens again, fresh, with one line saying so (the visitor only has
to try again); any other form gets the site's own 403 page, saying to reload and try again.
"""

from django.shortcuts import redirect, render

# The forms a visitor fills in before they are signed in, opened again rather than refused.
OPEN_AGAIN = ("/login/", "/register/", "/password-reset/")


def csrf_failure(request, reason=""):
    if request.method == "POST" and request.path in OPEN_AGAIN:
        return redirect(f"{request.path}?expired=1")
    return render(request, "403_csrf.html", status=403)
