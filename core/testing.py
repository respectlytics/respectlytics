"""What tests share: an in-memory stand-in for every cache the settings name (core/settings.py,
CACHES), so a test that swaps the database caches out swaps them all. The two share one store,
so `cache.clear()` between tests empties the rate limits' counts too, as it always has."""

LOCMEM = {
    "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
    "ratelimit": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"},
}
