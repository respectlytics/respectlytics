"""{% product_shot "paths" %}: a picture of the real product, one of the screenshots taken on the
invented sample app (assets/masters/product, built by manage.py build_images), with the phone's
own crop on a phone. The homepage shows them to sell the views, and an empty dashboard tab shows
its own, marked as an example, so a new developer sees what the tab will look like (owner,
2026-10-26). One registry of their files, sizes and words, so the two never disagree.
"""

from django import template

register = template.Library()

# name: (phone files, phone size), (wide files, wide size), what it shows
SHOTS = {
    "overview": (
        ("overview-phone-390", "overview-phone", 390, 780, 390, 590),
        ("overview-1120", "overview", 1120, 2240, 1200, 760),
        "The Respectlytics dashboard's Overview for a sleep sounds app over 30 days: events, "
        "sessions and the average session, last week's findings and a chart of each over time",
    ),
    "paths": (
        ("paths-phone-360", "paths-phone", 360, 720, 360, 482),
        ("paths-730", "paths", 730, 1460, 730, 390),
        "The Conversion tab's top conversion paths for a sleep sounds app: each path's events in "
        "order, ending in purchase, with how many sessions took it",
    ),
    "dropoffs": (
        ("dropoffs-phone-360", "dropoffs-phone", 360, 720, 360, 423),
        ("dropoffs-730", "dropoffs", 730, 1460, 730, 423),
        "The Conversion tab's drop-off points: the last event of sessions that ended without "
        "converting, ranked, as rose bars",
    ),
    "funnel": (
        ("funnel-phone-360", "funnel-phone", 360, 720, 360, 579),
        ("funnel-730", "funnel", 730, 1460, 730, 616),
        "A five-step funnel from app_open to purchase, each step's sessions as a bar with those "
        "lost since the step before drawn faint in rose",
    ),
    "drivers": (
        ("drivers-phone-360", "drivers-phone", 360, 720, 360, 412),
        ("drivers-730", "drivers", 730, 1460, 730, 412),
        "The Behavior tab: events whose sessions converted more often, each with its conversion "
        "rate with and without it as two bars",
    ),
    "segments": (
        ("segments-phone-360", "segments-phone", 360, 720, 360, 289),
        ("segments-730", "segments", 730, 1460, 730, 248),
        "The Segments tab: the overall conversion rate, the platform that converts best, and each "
        "platform's rate as a bar",
    ),
}


# The file for a browser that reads neither AVIF nor WebP (the overview has no JPEG)
FALLBACK = {"overview": "webp"}


@register.inclusion_tag("partials/product_shot.html")
def product_shot(name, sizes="(min-width: 1024px) 40rem, 100vw", eager=False, example=False):
    phone, wide, alt = SHOTS[name]
    return {
        "phone_small": phone[0],
        "phone_large": phone[1],
        "phone_small_w": phone[2],
        "phone_large_w": phone[3],
        "phone_w": phone[4],
        "phone_h": phone[5],
        "wide_small": wide[0],
        "wide_large": wide[1],
        "wide_small_w": wide[2],
        "wide_large_w": wide[3],
        "wide_w": wide[4],
        "wide_h": wide[5],
        "fallback": FALLBACK.get(name, "jpg"),
        "alt": f"An example on sample data: {alt[0].lower()}{alt[1:]}" if example else alt,
        "sizes": sizes,
        "eager": eager,
    }
